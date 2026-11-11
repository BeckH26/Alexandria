"""
providers/tokyoinsider.py - TokyoInsider Provider.
Scrapes anime series, episode listings, and direct media downloads
from TokyoInsider (tokyoinsider.com).
Uses Playwright browser automation with automated Cloudflare Turnstile bypass.
Downloads full MP4/MKV video files with streaming progress tracking, multi-language detection,
and sub/dub audio voice preference matching.
100% text-based with zero emojis.
"""

import os
import re
import time
import base64
import json
import tempfile
import atexit
import urllib.parse
import unicodedata
from typing import List, Dict, Any, Optional, Callable, Tuple
import requests
from tqdm import tqdm

def sanitize_filename(name: str, max_length: int = 100) -> str:
    """Sanitize string to be a safe filename for Windows, Linux, and macOS."""
    if not name:
        return "episode"
    name = name.replace('\u2013', '-').replace('\u2014', '-').replace('\u2015', '-')
    name = name.replace('\u2018', "'").replace('\u2019', "'")
    name = name.replace('\u201c', '').replace('\u201d', '')
    name = name.replace('\u00a0', ' ')
    clean = re.sub(r'[\\/*?:"<>|]', '_', name)
    clean = re.sub(r'[\s_]+', '_', clean).strip('._- ')
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip('._- ')
    return clean or "episode"

ARABIC_GROUPS = {
    "kaiyou", "anf", "al-asheq", "3asq", "mexat", "msoms", "arab", "arabic",
    "ara", "shahiid", "anime-down", "asq", "arab-anime"
}
ENGLISH_GROUPS = {
    "horriblesubs", "subsplease", "erai-raws", "judas", "ember", "commie",
    "coalgirls", "scy", "asenshi", "doki", "fff", "cleo", "kametsu", "bakedfish",
    "bluray-desu", "reaktor", "mtbb", "sg", "chyuu", "hatsuyuki", "whocares", "gg",
    "underwater", "nep_nep", "dragsterps", "golumpa", "davinci"
}


def clean_text(text: str) -> str:
    """Normalize unicode and strip unprintable characters for safe terminal output."""
    if not text:
        return ""
    replacements = {
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2014": "-", "\u2013": "-",
        "\u2026": "...", "\u00a0": " ",
        "\u00d7": "x", "\u2715": "x", "\u2716": "x"
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    text = unicodedata.normalize('NFKD', text)
    return text.encode('ascii', 'ignore').decode('ascii').strip()


def r13(s: str) -> str:
    """ROT13 cipher transformation used by TokyoInsider."""
    out = []
    for c in s:
        if 'a' <= c <= 'z':
            out.append(chr((ord(c) - 97 + 13) % 26 + 97))
        elif 'A' <= c <= 'Z':
            out.append(chr((ord(c) - 65 + 13) % 26 + 65))
        else:
            out.append(c)
    return ''.join(out)


def decode_tokyoinsider_link(data_a: str, data_b: str, key_k: str) -> str:
    """
    Decrypts obfuscated TokyoInsider download/navigation links using ROT13,
    base64 decoding, and XOR with key K.
    """
    s = r13((data_a + data_b)[::-1])
    pad = len(s) % 4
    if pad:
        s += '=' * (4 - pad)
    try:
        bin_data = base64.b64decode(s)
        return ''.join(chr(bin_data[i] ^ ord(key_k[i % len(key_k)])) for i in range(len(bin_data)))
    except Exception:
        return ""


def extract_key_from_html(html: str) -> str:
    """Extracts dynamic session key K from page script."""
    m = re.search(r'var\s+K\s*=\s*r13\(["\']([^"\']+)["\']\.split', html)
    if m:
        raw_k = m.group(1)
        return r13(raw_k[::-1])
    return ""


def sanitize_jellyfin_name(name: str, max_length: int = 120) -> str:
    """
    Sanitizes string for Jellyfin filename and folder standards.
    Removes invalid characters: \\ / : * ? " < > | while preserving readable spaces and hyphens.
    """
    if not name:
        return "Episode"
    name = name.replace('\u2013', '-').replace('\u2014', '-').replace('\u2015', '-')
    name = name.replace('\u2018', "'").replace('\u2019', "'")
    name = name.replace('\u201c', '').replace('\u201d', '')
    name = name.replace('\u00a0', ' ')
    name = name.replace(':', ' - ')
    clean = re.sub(r'[\\/*?"<>|]', '', name)
    clean = re.sub(r'\s+', ' ', clean).strip(' ._-')
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip(' ._-')
    return clean or "Episode"


def clean_series_title_and_year(title: str, vintage: str = "") -> Tuple[str, Optional[str]]:
    """
    Extracts base show title and release year for standard Jellyfin folder & file naming.
    Strips redundant suffixes like (TV), (TV 2011), (Movie), (OVA).
    """
    clean = re.sub(r'\s*\((?:TV|Movie|OVA)\s*\d*\)\s*', ' ', title, flags=re.I).strip()
    clean = re.sub(r'\s+', ' ', clean).strip()

    # Check if year is already enclosed in parentheses: e.g. "Hunter x Hunter (2011)"
    m_year_title = re.search(r'\(\s*(19\d\d|20\d\d)\s*\)', clean)
    if m_year_title:
        year = m_year_title.group(1)
        base = re.sub(r'\s*\(\s*' + year + r'\s*\)', '', clean).strip()
        return sanitize_jellyfin_name(base), year

    # If year is in title without parentheses: e.g. "Hunter x Hunter 2011"
    m_year_plain = re.search(r'\b(19\d\d|20\d\d)\b', clean)
    if m_year_plain:
        year = m_year_plain.group(1)
        base = re.sub(r'\b' + year + r'\b', '', clean).strip()
        return sanitize_jellyfin_name(base), year

    # Otherwise check metadata vintage: "Fall 2020" -> "2020"
    if vintage:
        m_v = re.search(r'\b(19\d\d|20\d\d)\b', vintage)
        if m_v:
            return sanitize_jellyfin_name(clean), m_v.group(1)

    return sanitize_jellyfin_name(clean), None


def get_jellyfin_series_folder_name(title: str, vintage: str = "") -> str:
    """Returns Jellyfin-standard series directory name: Series Name (Year)"""
    base, year = clean_series_title_and_year(title, vintage)
    return f"{base} ({year})" if year else base


def get_jellyfin_episode_path(
    series_title: str,
    vintage: str,
    ep_num: int,
    ep_title: str,
    ext: str = ".mp4",
    is_special: bool = False
) -> Tuple[str, str]:
    """
    Computes Jellyfin-compliant (season_folder, episode_filename).
    Spec: <Series Folder>/Season 01/<Series Name> (<Year>) - S01E01 - <Episode Title>.ext
          <Series Folder>/Season 00/<Series Name> (<Year>) - S00E01 - <Special Title>.ext
    """
    base, year = clean_series_title_and_year(series_title, vintage)
    show_label = f"{base} ({year})" if year else base

    if is_special or (ep_num >= 1000 and is_special):
        season_folder = "Season 00"
        if 1000 <= ep_num < 2000:
            spec_num = ep_num - 1000
            type_name = "Special"
        elif 2000 <= ep_num < 3000:
            spec_num = ep_num - 2000
            type_name = "Movie"
        elif 3000 <= ep_num < 4000:
            spec_num = ep_num - 3000
            type_name = "OVA"
        else:
            spec_num = ep_num
            type_name = "Special"
        s_tag = f"S00E{spec_num:02d}"

        clean_ep = re.sub(r'^.*?episode\s*\d+\s*', '', ep_title, flags=re.I).strip()
        title_part = f" - {clean_ep}" if clean_ep and len(clean_ep) > 2 else f" - {type_name} {spec_num}"
    else:
        season_folder = "Season 01"
        s_tag = f"S01E{ep_num:02d}"
        clean_ep = re.sub(r'^.*?episode\s*\d+\s*', '', ep_title, flags=re.I).strip()
        if clean_ep and clean_ep.lower() != f"episode {ep_num}" and len(clean_ep) > 1:
            title_part = f" - {clean_ep}"
        else:
            title_part = ""

    ext_clean = ext if ext.startswith('.') else f".{ext}"
    filename = sanitize_jellyfin_name(f"{show_label} - {s_tag}{title_part}") + ext_clean
    return season_folder, filename


class TokyoInsiderProvider:
    """
    Provider for searching, browsing, and downloading anime from TokyoInsider
    powered by Scrapling StealthySession.
    """

    NAME = "TokyoInsider"
    BASE_URL = "https://www.tokyoinsider.com"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://www.tokyoinsider.com/",
        "Accept": "*/*"
    }

    def __init__(self, profile_dir: Optional[str] = None):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._pw = None
        self._context = None
        self._page = None
        self._kitsu = None
        self._catalog = None
        self._local_catalog_file = os.path.join(os.path.dirname(__file__), "tokyoinsider_catalog.json")
        self._catalog_file = os.path.join(tempfile.gettempdir(), "tokyoinsider_catalog_v2.json")
        self._browse_cache: Dict[Tuple[Any, ...], List[Dict[str, Any]]] = {}
        atexit.register(self.close_browser)

    def _get_kitsu(self):
        """Lazy-initialize Kitsu client for intelligent query expansion."""
        if self._kitsu is None:
            try:
                from kitsu.client import KitsuClient
                self._kitsu = KitsuClient()
            except Exception:
                self._kitsu = None
        return self._kitsu

    def _get_browser_page(self):
        """Lazy-initialize and return persistent Playwright page with isolated profile to prevent session lock conflicts."""
        if self._pw is None:
            from playwright.sync_api import sync_playwright
            self._pw = sync_playwright().start()
        if self._context is None:
            profile_dir = os.path.join(tempfile.gettempdir(), f"tokyoinsider_profile_{os.getpid()}_{int(time.time())}")
            os.makedirs(profile_dir, exist_ok=True)
            launch_args = [
                "--disable-blink-features=AutomationControlled"
            ]
            try:
                self._context = self._pw.chromium.launch_persistent_context(
                    user_data_dir=profile_dir,
                    headless=True,
                    args=launch_args
                )
            except Exception:
                try:
                    browser = self._pw.chromium.launch(headless=True, args=launch_args)
                    self._context = browser.new_context()
                except Exception:
                    raise RuntimeError("Headless browser could not be initialized.")

            self._page = self._context.pages[0] if self._context.pages else self._context.new_page()
        return self._page

    def _solve_cf(self, page, timeout: int = 15) -> bool:
        """Solves Cloudflare Turnstile challenge if present."""
        t_end = time.time() + timeout
        while time.time() < t_end:
            try:
                t = page.title().lower()
            except Exception:
                t = ""
            if "just a moment" not in t and "security" not in t:
                try:
                    page.wait_for_load_state("domcontentloaded", timeout=3000)
                except Exception:
                    pass
                return True
            try:
                for f in page.frames:
                    if any(k in f.url for k in ["cloudflare", "challenges", "turnstile"]):
                        try:
                            cb = f.locator("input[type='checkbox']").first
                            if cb.is_visible():
                                cb.click(force=True)
                            else:
                                wrapper = f.locator("#challenge-stage, .ctp-checkbox-label, body").first
                                if wrapper.is_visible():
                                    wrapper.click(force=True)
                        except Exception:
                            pass
            except Exception:
                pass
            time.sleep(0.4)
        return False

    def fetch_page_html(self, url: str, timeout: int = 30) -> str:
        """Loads URL via browser context, solves Cloudflare, and returns full HTML."""
        page = self._get_browser_page()
        try:
            page.goto(url, timeout=timeout * 1000)
            self._solve_cf(page)
            time.sleep(0.5)
            return page.content()
        except Exception:
            try:
                self.close_browser()
                page = self._get_browser_page()
                page.goto(url, timeout=timeout * 1000)
                self._solve_cf(page)
                time.sleep(0.5)
                return page.content()
            except Exception:
                return ""

    def close_browser(self):
        """Cleanly close browser context and free resources."""
        if self._context is not None:
            try:
                self._context.close()
            except Exception:
                pass
            self._context = None
            self._page = None
        if self._pw is not None:
            try:
                self._pw.stop()
            except Exception:
                pass
            self._pw = None

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close_browser()

    def _ensure_catalog(self) -> List[Dict[str, Any]]:
        """Loads the full TokyoInsider A-Z anime catalog from local storage, disk cache, or fetches from site."""
        if self._catalog and len(self._catalog) > 500:
            return self._catalog

        # 1. Check bundled/local package catalog
        if os.path.exists(self._local_catalog_file):
            try:
                with open(self._local_catalog_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data and isinstance(data, list) and len(data) > 1000:
                        self._catalog = data
                        return self._catalog
            except Exception:
                pass

        # 2. Check temp disk cache (< 24 hours old)
        if os.path.exists(self._catalog_file):
            try:
                mtime = os.path.getmtime(self._catalog_file)
                if (time.time() - mtime) < 86400:
                    with open(self._catalog_file, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if data and isinstance(data, list) and len(data) > 1000:
                            self._catalog = data
                            return self._catalog
            except Exception:
                pass

        # 3. Fetch from TokyoInsider anime/list
        page = self._get_browser_page()
        try:
            page.goto(f"{self.BASE_URL}/anime/list", timeout=30000)
            self._solve_cf(page)
            time.sleep(1.5)
            data = page.evaluate("""() => {
                const out = [];
                const seen = new Set();
                document.querySelectorAll("a[href*='/anime/']").forEach(a => {
                    const h = a.href;
                    const parts = h.split('/anime/')[1]?.split('/') || [];
                    if (parts.length === 2 && parts[0].length === 1 && !parts[1].startsWith('list') && !parts[1].startsWith('search')) {
                        const title = (a.innerText || '').trim();
                        if (title && !seen.has(parts[1])) {
                            seen.add(parts[1]);
                            out.push({title, slug: parts[1], letter: parts[0], url: h});
                        }
                    }
                });
                return out;
            }""")
            if data and len(data) > 500:
                self._catalog = data
                try:
                    with open(self._catalog_file, "w", encoding="utf-8") as f:
                        json.dump(data, f)
                except Exception:
                    pass
                return self._catalog
        except Exception:
            pass

        return []

    @staticmethod
    def extract_slug(input_str: str) -> Tuple[str, str]:
        """
        Extract clean anime letter and slug from URL or string.
        Returns (letter, slug).
        """
        s = input_str.strip()
        m = re.search(r'/anime/([A-Z0-9])(?:/([^/?#]+))?', s, re.IGNORECASE)
        if m:
            letter = m.group(1).upper()
            slug = m.group(2) or ""
            return letter, slug.rstrip('/')
        clean = s.strip('/\\')
        letter = clean[0].upper() if clean else "A"
        return letter, clean

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search anime series with intelligent English / Romaji / Alternate title expansion.
        Resolves queries like 'clasromm', 'classroom of the elite', 'demon slayer',
        'attack on titan', 'solo leveling' directly to their TokyoInsider titles.
        """
        query_clean = clean_text(query).strip()
        if not query_clean:
            return []

        q_lower = query_clean.lower()
        catalog = self._ensure_catalog()

        # 1. Expand query using Kitsu API
        kitsu = self._get_kitsu()
        kitsu_matches = []
        if kitsu is not None:
            try:
                k_res = kitsu.search_media(query_clean, limit=5)
                for r in k_res:
                    canon = clean_text(r.get("canonical_title") or "").strip()
                    titles = r.get("titles") or {}
                    en = clean_text(titles.get("en") or "").strip()
                    en_jp = clean_text(titles.get("en_jp") or "").strip()
                    abbrevs = [clean_text(a).strip() for a in (r.get("abbreviated_titles") or []) if a]
                    kitsu_matches.append({
                        "canonical": canon,
                        "en": en,
                        "en_jp": en_jp,
                        "abbrevs": abbrevs
                    })
            except Exception:
                pass

        # Collect search tokens and English alias mappings
        tokens = set()
        for w in re.findall(r'[a-zA-Z0-9]+', q_lower):
            if len(w) >= 3:
                tokens.add(w)

        en_mappings = {}
        for km in kitsu_matches:
            for val in [km["canonical"], km["en"], km["en_jp"]] + km["abbrevs"]:
                if not val:
                    continue
                for w in re.findall(r'[a-zA-Z0-9]+', val.lower()):
                    if len(w) >= 3:
                        tokens.add(w)
                if km["en"] and km["canonical"]:
                    en_mappings[km["canonical"].lower()] = km["en"]
                if km["en"] and km["en_jp"]:
                    en_mappings[km["en_jp"].lower()] = km["en"]

        scored = []
        seen_slugs = set()

        for anime in catalog:
            t = anime["title"].lower()
            score = 0

            # Exact query match
            if q_lower in t:
                score += 200

            # Token matching
            matched_toks = sum(1 for tok in tokens if tok in t)
            if matched_toks > 0:
                score += matched_toks * 25

            # Kitsu canonical / Romaji matches
            for km in kitsu_matches:
                c = km["canonical"].lower()
                if c:
                    clean_c = re.sub(r'\s*\([^)]*\)', '', c).strip()
                    if clean_c and clean_c in t:
                        score += 150
                ej = km["en_jp"].lower()
                if ej:
                    clean_ej = re.sub(r'\s*\([^)]*\)', '', ej).strip()
                    if clean_ej and clean_ej in t:
                        score += 150
                en = km["en"].lower()
                if en:
                    clean_en = re.sub(r'\s*\([^)]*\)', '', en).strip()
                    if clean_en and clean_en in t:
                        score += 150

            if score > 0:
                display_title = anime["title"]
                for target_jap, target_en in en_mappings.items():
                    clean_tj = re.sub(r'\s*\([^)]*\)', '', target_jap).strip()
                    if clean_tj and clean_tj in t:
                        if target_en.lower() not in t:
                            display_title = f"{target_en} ({anime['title']})"
                        break

                seen_slugs.add(anime["slug"])
                scored.append({
                    "score": score,
                    "title": display_title,
                    "raw_title": anime["title"],
                    "slug": anime["slug"],
                    "letter": anime["letter"],
                    "url": anime.get("url") or f"{self.BASE_URL}/anime/{anime['letter']}/{anime['slug']}",
                    "provider": "tokyoinsider",
                    "source": "TokyoInsider"
                })

        scored.sort(key=lambda x: x["score"], reverse=True)
        results = scored[:limit]

        # If catalog yielded fewer results than limit, query TokyoInsider search endpoint
        if len(results) < limit:
            search_terms = [query_clean]
            for km in kitsu_matches:
                if km["canonical"] and km["canonical"] not in search_terms:
                    w = km["canonical"].split()
                    if w:
                        search_terms.append(w[0])
            for st in search_terms[:3]:
                if len(results) >= limit:
                    break
                live_url = f"{self.BASE_URL}/anime/search?k={urllib.parse.quote(st)}"
                html = self.fetch_page_html(live_url)
                if not html:
                    continue
                matches = re.findall(
                    r'<a\s+href=[\'"]/anime/([A-Z0-9])/([^\'"]+)[\'"][^>]*>(.*?)</a>',
                    html,
                    re.IGNORECASE
                )
                for let, s_slug, raw_t in matches:
                    if "/" in s_slug or s_slug in seen_slugs or s_slug.startswith(('list', 'search', 'popular', 'new', 'reviews')):
                        continue
                    clean_t = clean_text(re.sub(r'<[^>]+>', '', raw_t))
                    if len(clean_t) > 2 and "episode" not in clean_t.lower() and "comment" not in clean_t.lower():
                        seen_slugs.add(s_slug)
                        results.append({
                            "title": clean_t,
                            "slug": s_slug,
                            "letter": let.upper(),
                            "url": f"{self.BASE_URL}/anime/{let.upper()}/{s_slug}",
                            "provider": "tokyoinsider",
                            "source": "TokyoInsider"
                        })
                        if len(results) >= limit:
                            break

        return results[:limit]

    def browse(
        self,
        category: str = "popular",
        letter: Optional[str] = None,
        page_num: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """
        Browse anime series by popular, new releases, A-Z directory, or letter.
        Supports seamless pagination with zero sidebar duplicate contamination.
        """
        cat_lower = (category or "popular").lower().strip()
        let_clean = letter.strip().upper() if letter else None

        # For letter or list: use local catalog directly for instant response!
        if let_clean or cat_lower == "list":
            catalog = self._ensure_catalog()
            if let_clean:
                all_items = [a for a in catalog if a.get("letter") == let_clean]
            else:
                all_items = catalog
            start_idx = max(0, (page_num - 1) * limit)
            end_idx = start_idx + limit
            return all_items[start_idx:end_idx]

        # For new releases
        if cat_lower == "new":
            cache_key = ("new", None)
            if cache_key not in self._browse_cache:
                html = self.fetch_page_html(f"{self.BASE_URL}/anime/new")
                if not html:
                    return []
                m_14 = re.findall(r'<a\s+href=[\'"]/anime/([A-Z0-9])/([^\'"]+)[\'"][^>]*style=[\'"][^\'"]*14px[^\'"]*[\'"][^>]*>(.*?)</a>', html, re.I)
                raw_matches = m_14 if m_14 else re.findall(r'<a\s+href=[\'"]/anime/([A-Z0-9])/([^\'"]+)[\'"][^>]*>(.*?)</a>', html, re.I)

                all_items = []
                seen = set()
                for let, slug, raw_title in raw_matches:
                    if slug in seen or slug.startswith(('list', 'search', 'popular', 'new', 'reviews')):
                        continue
                    clean_t = clean_text(re.sub(r'<[^>]+>', '', raw_title))
                    if len(clean_t) > 1 and "episode" not in clean_t.lower() and "comment" not in clean_t.lower():
                        seen.add(slug)
                        all_items.append({
                            "title": clean_t,
                            "slug": slug,
                            "letter": let.upper(),
                            "url": f"{self.BASE_URL}/anime/{let.upper()}/{slug}",
                            "provider": "tokyoinsider",
                            "source": "TokyoInsider"
                        })
                self._browse_cache[cache_key] = all_items

            all_items = self._browse_cache.get(cache_key, [])
            start_idx = max(0, (page_num - 1) * limit)
            end_idx = start_idx + limit
            return all_items[start_idx:end_idx]

        # For popular: TokyoInsider paginates via ?start={offset}
        cache_key = ("popular", page_num, limit)
        if cache_key not in self._browse_cache:
            start_offset = max(0, (page_num - 1) * limit)
            target_url = f"{self.BASE_URL}/anime/?start={start_offset}"
            html = self.fetch_page_html(target_url)
            if not html:
                return []

            m_14 = re.findall(r'<a\s+href=[\'"]/anime/([A-Z0-9])/([^\'"]+)[\'"][^>]*style=[\'"][^\'"]*14px[^\'"]*[\'"][^>]*>(.*?)</a>', html, re.I)
            items = []
            seen = set()
            for let, slug, raw_title in m_14:
                if slug in seen or slug.startswith(('list', 'search', 'popular', 'new', 'reviews')):
                    continue
                clean_t = clean_text(re.sub(r'<[^>]+>', '', raw_title))
                if len(clean_t) > 1 and "episode" not in clean_t.lower() and "comment" not in clean_t.lower():
                    seen.add(slug)
                    items.append({
                        "title": clean_t,
                        "slug": slug,
                        "letter": let.upper(),
                        "url": f"{self.BASE_URL}/anime/{let.upper()}/{slug}",
                        "provider": "tokyoinsider",
                        "source": "TokyoInsider"
                    })
                if len(items) >= limit:
                    break

            self._browse_cache[cache_key] = items

        return self._browse_cache.get(cache_key, [])

    def get_browse_count(self, category: str = "popular", letter: Optional[str] = None) -> int:
        """
        Get the total number of anime series available in a given browse category or letter.
        """
        cat_lower = (category or "popular").lower().strip()
        let_clean = letter.strip().upper() if letter else None
        if let_clean or cat_lower == "list":
            catalog = self._ensure_catalog()
            if let_clean:
                return len([a for a in catalog if a.get("letter") == let_clean])
            return len(catalog)
        elif cat_lower == "new":
            cache_key = ("new", None)
            if cache_key not in self._browse_cache:
                self.browse(category="new", page_num=1, limit=20)
            return len(self._browse_cache.get(cache_key, []))
        return 500

    def get_anime_details(self, slug_or_url: str) -> Dict[str, Any]:
        """
        Fetches detailed information for an anime series:
        Title, synopsis, creator, genres, age group, vintage, status, and full episode list.
        """
        letter, slug = self.extract_slug(slug_or_url)
        if slug_or_url.startswith("http"):
            anime_url = slug_or_url
        else:
            anime_url = f"{self.BASE_URL}/anime/{letter}/{slug}"

        html = self.fetch_page_html(anime_url)
        if not html:
            return {"error": "Failed to fetch anime page", "title": slug.replace('_', ' '), "episodes": []}

        # 1. Extract session key K
        k_key = extract_key_from_html(html)

        # 2. Extract metadata from info table
        def extract_field(label: str) -> str:
            m = re.search(rf'<b>{label}:?</b>\s*</td>\s*<td[^>]*>(.*?)</td>', html, re.DOTALL | re.IGNORECASE)
            if m:
                return clean_text(re.sub(r'<[^>]+>', ' ', m.group(1)))
            return ""

        title_raw = extract_field(r"Title\(s\)")
        title = title_raw.split('\n')[0].strip() if title_raw else slug.replace('_', ' ')
        creator = extract_field("Creator")
        genres_raw = extract_field("Genres")
        genres = [g.strip() for g in genres_raw.split(',') if g.strip()] if genres_raw else []
        age_group = extract_field("Age Group")
        vintage = extract_field("Vintage")
        status = extract_field("Status")
        summary = extract_field("Summary")

        # 3. Extract all episodes using data-a and data-b spans
        episodes = []
        seen_urls = set()

        raw_spans = re.findall(
            r'<span[^>]*data-a=[\'"]([^\'"]+)[\'"][^>]*data-b=[\'"]([^\'"]+)[\'"][^>]*>(.*?)</span>',
            html,
            re.DOTALL | re.IGNORECASE
        )
        for da, db, inner in raw_spans:
            clean_t = clean_text(re.sub(r'<[^>]+>', '', inner))
            decoded_path = decode_tokyoinsider_link(da, db, k_key) if k_key else ""
            if not decoded_path:
                continue

            full_ep_url = decoded_path if decoded_path.startswith("http") else f"{self.BASE_URL}{decoded_path}"
            if full_ep_url in seen_urls:
                continue
            seen_urls.add(full_ep_url)

            # Determine episode number
            m_num = re.search(r'episode\s+(\d+)', clean_t, re.IGNORECASE)
            m_sp = re.search(r'special\s+(\d+)', clean_t, re.IGNORECASE)
            m_mov = re.search(r'movie\s+(\d+)', clean_t, re.IGNORECASE)
            m_ova = re.search(r'ova\s+(\d+)', clean_t, re.IGNORECASE)
            is_special = (bool(m_sp) or bool(m_mov) or bool(m_ova)) and not m_num
            if m_num:
                ep_num = int(m_num.group(1))
            elif m_sp:
                ep_num = 1000 + int(m_sp.group(1))
            elif m_mov:
                ep_num = 2000 + int(m_mov.group(1))
            elif m_ova:
                ep_num = 3000 + int(m_ova.group(1))
            else:
                m_any = re.search(r'(\d+)', clean_t)
                ep_num = int(m_any.group(1)) if m_any else len(episodes) + 1

            episodes.append({
                "title": clean_t,
                "number": ep_num,
                "url": full_ep_url,
                "is_special": is_special
            })

        # Sort episodes ascending (Episode 1 to Episode N, then specials)
        episodes.sort(key=lambda x: x["number"])

        return {
            "title": clean_text(title),
            "slug": slug,
            "letter": letter,
            "url": anime_url,
            "creator": creator,
            "genres": genres,
            "age_group": age_group,
            "vintage": vintage,
            "status": status,
            "summary": summary,
            "total_episodes": len(episodes),
            "episodes": episodes
        }

    def get_episode_download_sources(self, episode_url: str, retries: int = 2) -> List[Dict[str, Any]]:
        """
        Visits an episode page, decrypts all download links, and returns available video sources.
        Extracts direct media CDN URLs on media.tokyoinsider.com:8383 with resolution, size, and tags.
        """
        for attempt in range(1, retries + 1):
            try:
                html = self.fetch_page_html(episode_url)
                if not html:
                    if attempt < retries:
                        time.sleep(1.5)
                        continue
                    return []

                k_key = extract_key_from_html(html)

                # Find all .dlk spans with data-a and data-b
                candidates = []
                tags = list(re.finditer(r'<span\s+[^>]*class=[\'"][^\'"]*dlk[^\'"]*[\'"][^>]*>', html, re.IGNORECASE))
                for m in tags:
                    tag_str = m.group(0)
                    da_m = re.search(r'data-a=[\'"]([^\'"]+)[\'"]', tag_str, re.IGNORECASE)
                    db_m = re.search(r'data-b=[\'"]([^\'"]+)[\'"]', tag_str, re.IGNORECASE)
                    if da_m and db_m:
                        candidates.append((da_m.group(1), db_m.group(1), m.end()))

                if not candidates:
                    all_spans = list(re.finditer(r'<span\s+[^>]*data-a=[\'"]([^\'"]+)[\'"][^>]*data-b=[\'"]([^\'"]+)[\'"][^>]*>', html, re.IGNORECASE))
                    for m in all_spans:
                        candidates.append((m.group(1), m.group(2), m.end()))

                if not k_key or not candidates:
                    if attempt < retries:
                        time.sleep(1.5)
                        continue
                    return []

                sources = []
                for da, db, end_pos in candidates:
                    media_url = decode_tokyoinsider_link(da, db, k_key)
                    if not media_url or not media_url.startswith("http"):
                        continue

                    # Clean filename
                    raw_filename = media_url.split('/')[-1].split('?')[0]
                    clean_filename = clean_text(urllib.parse.unquote(raw_filename))

                    size_str = ""
                    dl_count = 0
                    uploader = ""
                    clean_surrounding = ""
                    if end_pos > 0:
                        surrounding = html[end_pos:end_pos + 800]
                        clean_surrounding = re.sub(r'<[^>]+>', ' ', surrounding)
                        size_m = re.search(r'Size:\s*([\d\.]+\s*(?:MB|GB|KB|Bytes))', clean_surrounding, re.IGNORECASE)
                        size_str = size_m.group(1).strip() if size_m else ""
                        dl_m = re.search(r'Downloads:\s*(\d+)', clean_surrounding, re.IGNORECASE)
                        dl_count = int(dl_m.group(1)) if dl_m else 0
                        up_m = re.search(r'Uploader:\s*([^\s\n\r]+)', clean_surrounding, re.IGNORECASE)
                        uploader = clean_text(up_m.group(1)) if up_m else ""

                    fn_lower = clean_filename.lower()
                    surr_lower = clean_surrounding.lower()
                    combined = f"{fn_lower} {surr_lower}"

                    # Detect voice type (Sub, Dub, Dual Audio)
                    if any(k in combined for k in ["dual audio", "dual-audio", "dual"]):
                        voice_type = "Dual Audio"
                    elif any(k in combined for k in ["dub", "dubbed", "english dub", "eng dub", "eng-dub", "animax", "funimation"]):
                        voice_type = "Dub"
                    else:
                        voice_type = "Sub"

                    # Detect subtitle language and release group
                    if any(k in fn_lower for k in ARABIC_GROUPS) or re.search(r'[-_\s\(\[]ar(?:ab|abic)?[-_\s\)\]]', fn_lower):
                        sub_lang = "Arabic"
                    elif any(k in fn_lower for k in ["vostfr", "french", "fra", "wakanim", "adn"]):
                        sub_lang = "French"
                    elif any(k in fn_lower for k in ["spanish", "espanol", "castellano", "latino", "puar", "apocalypse", "inu-fansub"]):
                        sub_lang = "Spanish"
                    elif any(k in fn_lower for k in ["german", "ger-sub", "ger-dub", "deutsch"]):
                        sub_lang = "German"
                    elif any(k in fn_lower for k in ["italian", "ita"]):
                        sub_lang = "Italian"
                    elif any(k in fn_lower for k in ["portuguese", "pt-br", "pt"]):
                        sub_lang = "Portuguese"
                    elif any(k in fn_lower for k in ["russian", "rus"]):
                        sub_lang = "Russian"
                    elif any(k in fn_lower for k in ["multi-subs", "multi-sub", "multisubs", "multisub", "multiple subtitle"]):
                        sub_lang = "Multi-Subs"
                    elif any(k in fn_lower for k in ENGLISH_GROUPS) or any(k in combined for k in ["eng", "english", "engsub", "eng-sub"]):
                        sub_lang = "English"
                    else:
                        sub_lang = "English"

                    if voice_type == "Dual Audio":
                        lang_label = "Dual Audio (ENG/JPN)"
                    elif voice_type == "Dub":
                        lang_label = "English Dub"
                    else:
                        lang_label = f"{sub_lang} Sub"

                    tags_list = []
                    if "1080" in fn_lower:
                        tags_list.append("1080p")
                    elif "720" in fn_lower:
                        tags_list.append("720p")
                    elif "480" in fn_lower:
                        tags_list.append("480p")

                    if "bluray" in fn_lower or "remux" in fn_lower or "bd" in fn_lower:
                        tags_list.append("Bluray")
                    tags_list.append(lang_label)

                    ext = os.path.splitext(clean_filename)[1].lower() or ".mp4"

                    sources.append({
                        "filename": clean_filename,
                        "media_url": media_url,
                        "url": media_url,
                        "size_str": size_str,
                        "downloads": dl_count,
                        "uploader": uploader,
                        "tags": tags_list,
                        "voice_type": voice_type,
                        "sub_lang": sub_lang,
                        "lang_label": lang_label,
                        "ext": ext
                    })

                if sources:
                    # Default rank: English Sub / Dual Audio, high resolution
                    sources.sort(key=lambda s: TokyoInsiderProvider.score_single_source(s, "english", "sub", "best"), reverse=True)
                    return sources

            except Exception:
                if attempt < retries:
                    time.sleep(1.5)
                    continue

        return []

    @staticmethod
    def source_rank_key(
        s: Dict[str, Any],
        target_lang: str = "english",
        voice_pref: str = "sub",
        quality: str = "best"
    ) -> Tuple[int, int, int, int]:
        """
        Calculates a strict 4-tuple lexicographical ranking key:
          (Priority 1: Language, Priority 2: Sub/Dub Voice, Priority 3: Quality, Priority 4: Bonus)
        Ensures strict layered ordering:
          1st: Target Language (never overridden by voice or resolution)
          2nd: Sub vs Dub voice preference
          3rd: Quality / Resolution (with closest graceful fallback)
          4th: Container and popularity tie-breaker
        """
        sub_lang = (s.get("sub_lang") or "English").lower()
        voice_type = (s.get("voice_type") or "Sub").lower()
        tags_str = " ".join(s.get("tags", [])).lower()
        fn_lower = s.get("filename", "").lower()

        # Priority 1: Language Matching (-10 to +10)
        t_lang = (target_lang or "english").lower().strip()
        if t_lang in ["english", "eng"]:
            if any(k in fn_lower for k in ARABIC_GROUPS) or re.search(r'[-_\s\(\[]ar(?:ab|abic)?[-_\s\)\]]', fn_lower):
                p1_lang = -10
            elif any(k in fn_lower for k in ["spanish", "espanol", "french", "vostfr", "german", "italian", "portuguese", "russian"]):
                p1_lang = -8
            elif any(k in sub_lang for k in ["arabic", "spanish", "french", "german", "italian", "portuguese", "russian"]):
                p1_lang = -10
            elif "multi" in sub_lang or "multi-sub" in fn_lower:
                p1_lang = 9
            elif any(k in fn_lower for k in ENGLISH_GROUPS) or any(k in fn_lower for k in ["eng", "english", "engsub", "eng-sub"]):
                p1_lang = 10
            else:
                p1_lang = 8
        elif t_lang != "any":
            if t_lang in sub_lang or t_lang in fn_lower:
                p1_lang = 10
            elif "multi" in sub_lang:
                p1_lang = 5
            else:
                p1_lang = -10
        else:
            p1_lang = 10

        # Priority 2: Sub vs Dub Voice Preference (-10 to +10)
        v_pref = (voice_pref or "sub").lower().strip()
        if v_pref == "sub":
            if "sub" in voice_type and "dub" not in tags_str:
                p2_voice = 10
            elif "dual" in voice_type:
                p2_voice = 9
            elif "dub" in voice_type:
                p2_voice = -5
            else:
                p2_voice = 5
        elif v_pref == "dub":
            if "dub" in voice_type:
                p2_voice = 10
            elif "dual" in voice_type:
                p2_voice = 9
            elif "sub" in voice_type:
                p2_voice = -5
            else:
                p2_voice = 0
        elif v_pref == "dual":
            if "dual" in voice_type:
                p2_voice = 10
            elif "dub" in voice_type:
                p2_voice = 6
            elif "sub" in voice_type:
                p2_voice = 4
            else:
                p2_voice = 2
        else:
            p2_voice = 10

        # Priority 3: Quality / Resolution (10 to 100)
        res = TokyoInsiderProvider.get_source_res(s)
        q_target = (quality or "best").lower().strip()
        if q_target == "1080p":
            if res == "1080p":
                p3_quality = 100
            elif res == "720p":
                p3_quality = 75
            elif res == "480p":
                p3_quality = 50
            else:
                p3_quality = 25
        elif q_target == "720p":
            if res == "720p":
                p3_quality = 100
            elif res == "1080p":
                p3_quality = 75
            elif res == "480p":
                p3_quality = 50
            else:
                p3_quality = 25
        elif q_target == "480p":
            if res == "480p":
                p3_quality = 100
            elif res == "720p":
                p3_quality = 75
            elif res == "1080p":
                p3_quality = 50
            else:
                p3_quality = 40
        else:
            if res == "1080p":
                p3_quality = 100
            elif res == "720p":
                p3_quality = 80
            elif res == "480p":
                p3_quality = 50
            else:
                p3_quality = 25

        # Priority 4: Bonus / Tie-Breaker (0 to 30)
        p4_bonus = 0
        if s.get("ext") in [".mp4", ".mkv"]:
            p4_bonus += 10
        if "bluray" in tags_str or "bd" in tags_str:
            p4_bonus += 5
        p4_bonus += min(s.get("downloads", 0) // 20, 10)

        return (p1_lang, p2_voice, p3_quality, p4_bonus)

    @classmethod
    def score_single_source(
        cls,
        s: Dict[str, Any],
        target_lang: str = "english",
        voice_pref: str = "sub",
        quality: str = "best"
    ) -> int:
        """
        Converts the hierarchical rank tuple into a unified integer score.
        Language is weighted at 100,000x, Voice at 1,000x, Quality at 10x, Bonus at 1x.
        """
        k = cls.source_rank_key(s, target_lang=target_lang, voice_pref=voice_pref, quality=quality)
        return k[0] * 100000 + k[1] * 1000 + k[2] * 10 + k[3]

    @staticmethod
    def get_source_res(s: Dict[str, Any]) -> str:
        """Determines the resolution string (1080p, 720p, 480p, or SD) of a source."""
        tags_str = " ".join(s.get("tags", [])).lower()
        fn_lower = s.get("filename", "").lower()
        if "1080" in tags_str or "1080" in fn_lower:
            return "1080p"
        if "720" in tags_str or "720" in fn_lower:
            return "720p"
        if "480" in tags_str or "480" in fn_lower:
            return "480p"
        return "SD"

    @classmethod
    def select_best_source(
        cls,
        sources: List[Dict[str, Any]],
        target_lang: str = "english",
        voice_pref: str = "sub",
        quality: str = "best"
    ) -> Dict[str, Any]:
        """
        Selects the optimal source matching language (1st), voice sub/dub (2nd), and quality (3rd).
        """
        if not sources:
            return {}
        sorted_sources = sorted(
            sources,
            key=lambda s: cls.source_rank_key(s, target_lang=target_lang, voice_pref=voice_pref, quality=quality),
            reverse=True
        )
        return sorted_sources[0]

    @staticmethod
    def is_episode_downloaded(series_dir: str, ep_num: int, is_special: bool = False) -> Optional[str]:
        """
        Checks whether a complete video file for ep_num already exists in series_dir
        either in Jellyfin season folders (Season 01, Season 00) or legacy flat structure.
        """
        if not os.path.isdir(series_dir):
            return None

        video_files = []
        for root, dirs, files in os.walk(series_dir):
            for fn in files:
                if fn.endswith(".part"):
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext not in [".mp4", ".mkv", ".avi", ".webm"]:
                    continue
                fp = os.path.join(root, fn)
                try:
                    if os.path.getsize(fp) >= 1024 * 512:
                        video_files.append((fn, fp))
                except OSError:
                    pass

        # 1. Check Jellyfin tags: S01E01, S00E01, etc.
        if is_special or (ep_num >= 1000 and is_special):
            if 1000 <= ep_num < 2000:
                s_spec = ep_num - 1000
            elif 2000 <= ep_num < 3000:
                s_spec = ep_num - 2000
            elif 3000 <= ep_num < 4000:
                s_spec = ep_num - 3000
            else:
                s_spec = ep_num
            target_tags = [f"s00e{s_spec:02d}", f"s00e{s_spec:03d}", f"s00e{s_spec}"]
        else:
            target_tags = [f"s01e{ep_num:02d}", f"s01e{ep_num:03d}", f"s01e{ep_num}"]

        for fn, fp in video_files:
            fn_lower = fn.lower()
            for tag in target_tags:
                if tag in fn_lower:
                    return os.path.relpath(fp, series_dir)

        # 2. Check legacy naming conventions
        str_num_3 = f"{ep_num:03d}"
        str_num_2 = f"{ep_num:02d}"
        str_num_1 = str(ep_num)

        for fn, fp in video_files:
            fn_lower = fn.lower()
            has_special_tag = any(k in fn_lower for k in ["movie", "special", "ova", "film"])
            if not is_special and has_special_tag and ep_num < 1000:
                continue

            if f"episode_{str_num_3}_" in fn_lower or f"episode_{str_num_2}_" in fn_lower or f"episode_{str_num_1}_" in fn_lower:
                return os.path.relpath(fp, series_dir)
            if f"episode {str_num_3}" in fn_lower or f"episode {str_num_2}" in fn_lower or f"episode {str_num_1}" in fn_lower:
                return os.path.relpath(fp, series_dir)

            m = re.search(r'[-_\s]0*' + re.escape(str_num_1) + r'[-_\s\(\[]', fn)
            if m:
                return os.path.relpath(fp, series_dir)

        return None

    def download_file(
        self,
        media_url: str,
        output_path: str,
        overwrite: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> bool:
        """
        Direct high-speed streaming download of an anime episode file.
        Uses temporary .part file and atomic rename upon completion.
        """
        if os.path.exists(output_path) and not overwrite and os.path.getsize(output_path) > 1024:
            return True

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        part_path = f"{output_path}.part"

        headers = {
            "User-Agent": self.HEADERS["User-Agent"],
            "Referer": "https://www.tokyoinsider.com/"
        }

        try:
            with self.session.get(media_url, stream=True, timeout=60, headers=headers) as resp:
                resp.raise_for_status()
                total_bytes = int(resp.headers.get("Content-Length", 0))

                desc_name = os.path.basename(output_path)
                if len(desc_name) > 35:
                    desc_name = desc_name[:32] + "..."

                with open(part_path, "wb") as f, tqdm(
                    total=total_bytes,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=desc_name,
                    ncols=80,
                    leave=False
                ) as pbar:
                    downloaded = 0
                    last_cb_time = 0.0
                    for chunk in resp.iter_content(chunk_size=1048576):
                        if not chunk:
                            break
                        f.write(chunk)
                        downloaded += len(chunk)
                        pbar.update(len(chunk))
                        now = time.time()
                        if progress_callback and total_bytes > 0 and (now - last_cb_time >= 0.25 or downloaded == total_bytes):
                            last_cb_time = now
                            progress_callback({
                                "event": "download_progress",
                                "downloaded": downloaded,
                                "total": total_bytes,
                                "percent": round((downloaded / total_bytes) * 100, 1)
                            })

            if os.path.exists(part_path):
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(part_path, output_path)
                return True
            return False
        except Exception:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except Exception:
                    pass
            return False

    def download_anime(
        self,
        slug_or_url: str,
        start_ep: int = 1,
        end_ep: Optional[int] = None,
        quality: str = "best",
        language: str = "english",
        voice_pref: str = "sub",
        strict_voice: bool = False,
        output_dir: str = "anime_files",
        overwrite: bool = False,
        delay: float = 0.5,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Batch downloader for anime series from TokyoInsider using Scrapling.
        Selects best media sources and downloads into output_dir/<Anime Title>/.
        """
        details = self.get_anime_details(slug_or_url)
        anime_title = details.get("title") or "Anime"
        episodes = details.get("episodes", [])

        if not episodes:
            return {
                "title": anime_title,
                "downloaded": 0,
                "skipped": 0,
                "failed": 0,
                "total": 0,
                "series_folder": "",
                "error": "No episodes found for anime"
            }

        # Filter episode range
        selected = []
        for ep in episodes:
            num = ep.get("number", 0)
            if num >= start_ep:
                if end_ep is None or num <= end_ep:
                    selected.append(ep)

        # Jellyfin Series Directory Name: <Series Name> (<Year>)
        vintage = details.get("vintage", "")
        jellyfin_folder = get_jellyfin_series_folder_name(anime_title, vintage)
        series_dir = os.path.join(output_dir, jellyfin_folder)
        os.makedirs(series_dir, exist_ok=True)

        stats = {
            "title": anime_title,
            "downloaded": 0,
            "skipped": 0,
            "failed": 0,
            "total": len(selected),
            "series_folder": series_dir
        }

        print(f"\nDownloading '{anime_title}': {len(selected)} episode(s) to '{series_dir}' [Jellyfin Structure]...")

        for idx, ep in enumerate(selected, 1):
            ep_num = ep.get("number", idx)
            ep_title = ep.get("title", f"Episode {ep_num}")
            ep_url = ep.get("url")
            is_special = ep.get("is_special", False)

            # Check if episode is already downloaded in Jellyfin Season folders or legacy paths
            if not overwrite:
                existing_fn = self.is_episode_downloaded(series_dir, ep_num, is_special=is_special)
                if not existing_fn:
                    legacy_dir = os.path.join(output_dir, sanitize_filename(anime_title, max_length=60))
                    if legacy_dir != series_dir and os.path.isdir(legacy_dir):
                        existing_fn = self.is_episode_downloaded(legacy_dir, ep_num, is_special=is_special)
                if existing_fn:
                    print(f"[{idx}/{len(selected)}] {ep_title} -> [SKIP] Already downloaded: {existing_fn}")
                    stats["skipped"] += 1
                    continue

            print(f"[{idx}/{len(selected)}] Resolving {ep_title}...")

            sources = self.get_episode_download_sources(ep_url)
            if not sources:
                time.sleep(2.0)
                sources = self.get_episode_download_sources(ep_url, retries=2)

            if not sources:
                print(f"  [ERROR] No media sources found for {ep_title}.")
                stats["failed"] += 1
                continue

            # Pick best source matching language, voice (sub/dub), and quality preferences
            chosen_source = self.select_best_source(
                sources,
                target_lang=language,
                voice_pref=voice_pref,
                quality=quality
            )

            chosen_voice = chosen_source.get("voice_type", "Sub")
            v_req = (voice_pref or "sub").lower().strip()
            if v_req == "dub" and chosen_voice not in ("Dub", "Dual Audio"):
                if strict_voice:
                    print(f"  [SKIP - NO DUB] English Dub not available on TokyoInsider for {ep_title}.")
                    stats["skipped"] += 1
                    continue
                else:
                    print(f"  [VOICE FALLBACK] English Dub is not available on TokyoInsider for {ep_title} -> falling back to: {chosen_source.get('lang_label', 'English Sub')}")
            elif v_req == "dual" and chosen_voice != "Dual Audio":
                if strict_voice:
                    print(f"  [SKIP - NO DUAL AUDIO] Dual Audio not available on TokyoInsider for {ep_title}.")
                    stats["skipped"] += 1
                    continue
                else:
                    print(f"  [VOICE FALLBACK] Dual Audio is not available on TokyoInsider for {ep_title} -> falling back to: {chosen_source.get('lang_label', 'English Sub')}")

            chosen_res = self.get_source_res(chosen_source)
            q_req = (quality or "best").lower().strip()
            if q_req != "best" and chosen_res.lower() != q_req:
                lang_tag = chosen_source.get("lang_label", "Preferred Language")
                print(f"  [QUALITY FALLBACK] {q_req} not available ({lang_tag}) -> automatically downloading next best: {chosen_res}")

            ext = chosen_source.get("ext", ".mp4")
            season_folder, jellyfin_fn = get_jellyfin_episode_path(
                anime_title,
                vintage,
                ep_num,
                ep_title,
                ext=ext,
                is_special=is_special
            )
            season_dir = os.path.join(series_dir, season_folder)
            os.makedirs(season_dir, exist_ok=True)
            dest_path = os.path.join(season_dir, jellyfin_fn)
            dest_fn = os.path.join(season_folder, jellyfin_fn)

            if os.path.exists(dest_path) and not overwrite and os.path.getsize(dest_path) > 1024:
                print(f"  [SKIP] Already exists: {dest_fn}")
                stats["skipped"] += 1
                continue

            size_label = f" ({chosen_source.get('size_str')})" if chosen_source.get("size_str") else ""
            lang_label = f" [{chosen_source.get('lang_label', 'English Sub')}]" if chosen_source.get("lang_label") else ""
            print(f"  [DOWNLOAD] {dest_fn}{size_label}{lang_label}...")

            if progress_callback:
                progress_callback({
                    "event": "episode_start",
                    "episode_num": ep_num,
                    "total_episodes": len(selected),
                    "episode_title": ep_title,
                    "filename": dest_fn,
                    "voice_tag": chosen_source.get('lang_label', 'English Sub')
                })

            success = self.download_file(
                chosen_source["media_url"],
                dest_path,
                overwrite=overwrite,
                progress_callback=progress_callback
            )

            if success:
                stats["downloaded"] += 1
                print(f"  [OK] Saved (Jellyfin): {dest_fn}")
            else:
                stats["failed"] += 1
                print(f"  [FAILED] Failed to download {dest_fn}")

            if delay > 0:
                time.sleep(delay)

        return stats
