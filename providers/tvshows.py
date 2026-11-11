"""
providers/tvshows.py - TV Shows Provider for Alexandria Studio.
Provides search, full episode guides, and metadata via TVMaze API,
searches classic TV on Internet Archive, and manages Jellyfin-compliant
folder and file formatting for TV series.
100% text-based with zero emojis.
"""

import os
import re
import time
import unicodedata
from typing import List, Dict, Any, Optional, Tuple, Callable
import requests
from tqdm import tqdm


def clean_text(text: str) -> str:
    """Normalize unicode and strip unprintable characters for safe terminal output."""
    if not text:
        return ""
    replacements = {
        "\u2018": "'", "\u2019": "'",
        "\u201c": '"', "\u201d": '"',
        "\u2014": "-", "\u2013": "-",
        "\u2026": "...", "\u00a0": " "
    }
    for orig, repl in replacements.items():
        text = text.replace(orig, repl)
    text = unicodedata.normalize('NFKD', text)
    return text.encode('ascii', 'ignore').decode('ascii').strip()


def sanitize_jellyfin_name(name: str, max_length: int = 120) -> str:
    """
    Sanitizes string for Jellyfin filename / folder standards.
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


def get_jellyfin_tv_paths(
    series_title: str,
    year: Optional[str],
    season_num: int,
    ep_num: int,
    ep_title: str,
    ext: str = ".mp4"
) -> Tuple[str, str, str]:
    """
    Computes Jellyfin-compliant (series_folder, season_folder, episode_filename).
    Spec: <series_folder>/<season_folder>/<episode_filename>
    Example: Breaking Bad (2008)/Season 01/Breaking Bad (2008) - S01E01 - Pilot.mp4
    """
    clean_series = sanitize_jellyfin_name(series_title)
    if year and not re.search(r'\(\s*' + re.escape(year) + r'\s*\)', clean_series):
        series_folder = f"{clean_series} ({year})"
    else:
        series_folder = clean_series

    season_folder = f"Season {season_num:02d}" if season_num > 0 else "Season 00"
    s_tag = f"S{season_num:02d}E{ep_num:02d}"

    clean_ep = sanitize_jellyfin_name(ep_title) if ep_title else ""
    if clean_ep and clean_ep.lower() != f"episode {ep_num}" and clean_ep.lower() != f"episode {ep_num:02d}":
        title_part = f" - {clean_ep}"
    else:
        title_part = ""

    ext_clean = ext if ext.startswith('.') else f".{ext}"
    filename = f"{series_folder} - {s_tag}{title_part}{ext_clean}"
    return series_folder, season_folder, filename


class TVShowProvider:
    """
    TV Show metadata, episode guide, and Jellyfin download manager.
    Powered by TVMaze open API and Scrapling Fetcher.
    """

    NAME = "TVShows"
    TVMAZE_API = "https://api.tvmaze.com"
    ARCHIVE_API = "https://archive.org/advancedsearch.php"

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    def _fetch_json(self, url: str, timeout: int = 15) -> Optional[Any]:
        """Fetch JSON payload using standard requests with fallback."""
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        try:
            from scrapling.fetchers import Fetcher
            resp = Fetcher.get(url, impersonate="chrome", timeout=timeout)
            if resp.status == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def search(self, query: str, limit: int = 15) -> List[Dict[str, Any]]:
        """
        Search TV shows by title or keyword via TVMaze API.
        Returns comprehensive metadata including premiered year, rating, network, and genres.
        """
        q = query.strip()
        if not q:
            return []

        url = f"{self.TVMAZE_API}/search/shows?q={requests.utils.quote(q)}"
        data = self._fetch_json(url, timeout=15)
        if not data or not isinstance(data, list):
            return []

        results = []
        for item in data[:limit]:
            show = item.get("show", {})
            if not show or not show.get("name"):
                continue

            premiered = show.get("premiered") or ""
            year = premiered.split("-")[0] if premiered and len(premiered) >= 4 else None

            summary_raw = show.get("summary") or ""
            clean_summary = clean_text(re.sub(r'<[^>]+>', ' ', summary_raw)).strip()

            rating_obj = show.get("rating") or {}
            rating_val = rating_obj.get("average")
            rating_str = f"{rating_val:.1f}/10" if rating_val else "N/A"

            image_obj = show.get("image") or {}
            image_url = image_obj.get("medium") or image_obj.get("original") or ""

            network_obj = show.get("network") or show.get("webChannel") or {}
            network_name = network_obj.get("name") or "Broadcast"

            results.append({
                "id": show.get("id"),
                "title": clean_text(show.get("name")),
                "premiered": premiered,
                "year": year,
                "genres": show.get("genres", []),
                "status": show.get("status", "Unknown"),
                "rating": rating_str,
                "summary": clean_summary,
                "image_url": image_url,
                "network": network_name,
                "url": show.get("url") or f"https://www.tvmaze.com/shows/{show.get('id')}",
                "provider": "tvshows",
                "source": "TVMaze"
            })

        return results

    def get_show_details(self, show_id: int) -> Dict[str, Any]:
        """
        Fetch full TV show details including all seasons and episodes.
        """
        url = f"{self.TVMAZE_API}/shows/{show_id}?embed[]=episodes&embed[]=seasons"
        data = self._fetch_json(url, timeout=18)
        if not data or not isinstance(data, dict):
            return {"error": "Failed to fetch show details", "title": "Unknown", "seasons": [], "episodes": []}

        premiered = data.get("premiered") or ""
        year = premiered.split("-")[0] if premiered and len(premiered) >= 4 else None

        summary_raw = data.get("summary") or ""
        clean_summary = clean_text(re.sub(r'<[^>]+>', ' ', summary_raw)).strip()

        embedded = data.get("_embedded", {})
        raw_seasons = embedded.get("seasons", [])
        raw_episodes = embedded.get("episodes", [])

        # Process seasons
        seasons = []
        for s in raw_seasons:
            seasons.append({
                "number": s.get("number", 1),
                "episodes_count": s.get("episodeOrder") or 0,
                "premiere_date": s.get("premiereDate") or "",
                "end_date": s.get("endDate") or ""
            })

        # Process episodes
        episodes = []
        for ep in raw_episodes:
            s_num = ep.get("season", 1)
            e_num = ep.get("number", 1)
            ep_title = clean_text(ep.get("name") or f"Episode {e_num}")
            ep_summary = clean_text(re.sub(r'<[^>]+>', ' ', ep.get("summary") or "")).strip()
            ep_airdate = ep.get("airdate") or ""
            ep_runtime = ep.get("runtime") or 0

            episodes.append({
                "season": s_num,
                "number": e_num,
                "title": ep_title,
                "summary": ep_summary,
                "airdate": ep_airdate,
                "runtime": ep_runtime,
                "url": ep.get("url") or ""
            })

        return {
            "id": data.get("id"),
            "title": clean_text(data.get("name")),
            "premiered": premiered,
            "year": year,
            "genres": data.get("genres", []),
            "status": data.get("status", "Unknown"),
            "summary": clean_summary,
            "seasons": seasons,
            "episodes": episodes,
            "total_episodes": len(episodes)
        }

    def search_archive_shows(self, query: str, limit: int = 12) -> List[Dict[str, Any]]:
        """
        Search classic and complete TV series on Internet Archive with direct MP4 downloads.
        Queries television collections with popularity ranking (downloads desc) and smart title matching.
        """
        q_clean = clean_text(query).strip()
        if not q_clean:
            return []

        words = [w.strip() for w in q_clean.split() if w.strip()]
        if not words:
            return []

        # 1. Primary search: exact keyword matching on title field sorted by download popularity
        and_query = " AND ".join(f'title:({w})' for w in words)
        search_query = f'(mediatype:(movies) OR collection:(classic_tv) OR collection:(television)) AND ({and_query})'
        params = {
            "q": search_query,
            "fl[]": ["identifier", "title", "description", "year", "downloads"],
            "sort[]": "downloads desc",
            "rows": limit,
            "output": "json"
        }
        url = f"{self.ARCHIVE_API}?{requests.compat.urlencode(params, doseq=True)}"

        docs = []
        res1 = self._fetch_json(url, timeout=15)
        if res1 and isinstance(res1, dict):
            docs = res1.get("response", {}).get("docs", [])

        # 2. Fallback search: broader full-text search across archive if strict title yielded no hits
        if not docs:
            fallback_query = f'(mediatype:(movies) OR collection:(classic_tv) OR collection:(television)) AND ({q_clean})'
            params["q"] = fallback_query
            url = f"{self.ARCHIVE_API}?{requests.compat.urlencode(params, doseq=True)}"
            res2 = self._fetch_json(url, timeout=15)
            if res2 and isinstance(res2, dict):
                docs = res2.get("response", {}).get("docs", [])

        results = []
        seen = set()
        for d in docs:
            ident = d.get("identifier")
            if not ident or ident in seen:
                continue
            seen.add(ident)
            title = clean_text(d.get("title") or ident)
            desc = clean_text(re.sub(r'<[^>]+>', ' ', d.get("description") or "")).strip()
            year = d.get("year")
            dls = d.get("downloads", 0)

            results.append({
                "identifier": ident,
                "title": title,
                "year": str(year) if year else None,
                "downloads": dls,
                "summary": desc[:250] + ("..." if len(desc) > 250 else ""),
                "archive_url": f"https://archive.org/details/{ident}",
                "provider": "archive_tv"
            })

        return results

    def get_archive_mp4_files(self, identifier: str) -> List[Dict[str, Any]]:
        """
        Fetches direct MP4 download links for an Internet Archive item,
        naturally sorted by season and episode number.
        """
        url = f"https://archive.org/metadata/{identifier}"
        data = self._fetch_json(url, timeout=18)
        if not data or not isinstance(data, dict):
            return []

        files = data.get("files", [])

        mp4s = []
        for f in files:
            name = f.get("name", "")
            fmt = f.get("format", "")
            if name.lower().endswith(".mp4") or "mp4" in fmt.lower():
                sz_bytes = int(f.get("size", 0))
                if sz_bytes < 1024 * 1024:
                    continue
                sz_mb = sz_bytes / (1024 * 1024)
                direct_url = f"https://archive.org/download/{identifier}/{name}"
                mp4s.append({
                    "filename": name,
                    "url": direct_url,
                    "size_mb": sz_mb,
                    "format": fmt or "MP4"
                })

        # Natural sort key: SxxExx -> leading number ("01 Pilot") -> alphabetical
        def _sort_key(item):
            fn = item["filename"]
            m_se = re.search(r's(\d+)e(\d+)', fn, re.I)
            if m_se:
                return (0, int(m_se.group(1)), int(m_se.group(2)), fn)
            m_lead = re.search(r'(?:^|ep(?:isode)?[\s_-]*)0*(\d+)\b', fn, re.I)
            if m_lead:
                return (1, 1, int(m_lead.group(1)), fn)
            return (2, 0, 0, fn)

        mp4s.sort(key=_sort_key)
        return mp4s

    def is_episode_downloaded(
        self,
        series_dir: str,
        season_num: int,
        ep_num: int
    ) -> Optional[str]:
        """
        Checks whether S{season:02d}E{ep_num:02d} is already downloaded in series_dir.
        Checks both Jellyfin Season folders and root directory.
        """
        if not os.path.isdir(series_dir):
            return None

        target_tags = [
            f"s{season_num:02d}e{ep_num:02d}",
            f"s{season_num}e{ep_num:02d}",
            f"s{season_num:02d}e{ep_num}",
            f"s{season_num}e{ep_num}"
        ]

        for root, dirs, files in os.walk(series_dir):
            for fn in files:
                if fn.endswith(".part"):
                    continue
                ext = os.path.splitext(fn)[1].lower()
                if ext not in [".mp4", ".mkv", ".avi", ".webm"]:
                    continue
                fp = os.path.join(root, fn)
                try:
                    if os.path.getsize(fp) < 1024 * 512:
                        continue
                except OSError:
                    continue

                fn_lower = fn.lower()
                for tag in target_tags:
                    if tag in fn_lower:
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
        Direct high-speed streaming download of a video file with progress tracking.
        Uses temporary .part file and atomic rename upon completion.
        """
        if os.path.exists(output_path) and not overwrite and os.path.getsize(output_path) > 1024 * 512:
            return True

        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        part_path = f"{output_path}.part"

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
            "Referer": "https://archive.org/"
        }

        try:
            with self.session.get(media_url, stream=True, timeout=60, headers=headers) as resp:
                resp.raise_for_status()
                total_bytes = int(resp.headers.get("Content-Length", 0))

                downloaded = 0
                t0 = time.time()
                last_cb_time = 0.0

                with open(part_path, "wb") as f, tqdm(
                    total=total_bytes,
                    unit="B",
                    unit_scale=True,
                    unit_divisor=1024,
                    desc=os.path.basename(output_path)[:40],
                    leave=False
                ) as pbar:
                    for chunk in resp.iter_content(chunk_size=1024 * 1024):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            pbar.update(len(chunk))
                            now = time.time()
                            if progress_callback and (now - last_cb_time >= 0.25 or downloaded == total_bytes):
                                last_cb_time = now
                                elapsed = now - t0
                                speed = downloaded / max(0.001, elapsed)
                                progress_callback({
                                    "downloaded": downloaded,
                                    "total": total_bytes,
                                    "speed": speed,
                                    "filename": os.path.basename(output_path)
                                })

            if os.path.exists(part_path) and os.path.getsize(part_path) > 1024:
                if os.path.exists(output_path):
                    os.remove(output_path)
                os.rename(part_path, output_path)
                return True
            else:
                if os.path.exists(part_path):
                    os.remove(part_path)
                return False

        except Exception as e:
            if os.path.exists(part_path):
                try:
                    os.remove(part_path)
                except OSError:
                    pass
            print(f"Download error: {e}")
            return False

    def download_tv_episode(
        self,
        show_title: str,
        year: Optional[str],
        season_num: int,
        ep_num: int,
        ep_title: str,
        media_url: str,
        output_dir: str = "tv_files",
        overwrite: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Tuple[bool, str]:
        """
        Downloads a TV show episode into Jellyfin-compliant directory format:
        <output_dir>/<Show Title> (<Year>)/Season <01>/<Show Title> (<Year>) - S01E01 - <Title>.<ext>
        Returns (success: bool, saved_rel_path: str).
        """
        ext = os.path.splitext(media_url.split("?")[0])[1].lower() or ".mp4"
        series_folder, season_folder, filename = get_jellyfin_tv_paths(
            show_title, year, season_num, ep_num, ep_title, ext=ext
        )

        full_dir = os.path.join(output_dir, series_folder, season_folder)
        os.makedirs(full_dir, exist_ok=True)
        dest_path = os.path.join(full_dir, filename)
        rel_saved = os.path.join(series_folder, season_folder, filename)

        if not overwrite:
            existing = self.is_episode_downloaded(os.path.join(output_dir, series_folder), season_num, ep_num)
            if existing:
                return True, os.path.join(series_folder, existing)

        if progress_callback:
            progress_callback({
                "event": "episode_start",
                "episode_num": ep_num,
                "season_num": season_num,
                "filename": filename,
                "show_title": show_title
            })

        success = self.download_file(media_url, dest_path, overwrite=overwrite, progress_callback=progress_callback)
        return success, rel_saved
