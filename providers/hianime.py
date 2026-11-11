"""
providers/hianime.py - HiAnime Provider for English Dub & Sub anime streaming & downloads.
Scrapes anime series, episode listings, servers, and decrypts 1080p high-speed video streams
from HiAnime (hianime.at).
Provides full English Dubbed audio releases, Jellyfin library structuring,
and multi-threaded HLS streaming downloader.
100% text-based with zero emojis.
"""

import os
import re
import time
import base64
import json
import urllib.parse
import shutil
import subprocess
from typing import List, Dict, Any, Optional, Callable, Tuple
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED

import requests
from urllib3.util import Retry
from tqdm import tqdm
from bs4 import BeautifulSoup

from providers.tokyoinsider import (
    clean_text,
    get_jellyfin_series_folder_name,
    get_jellyfin_episode_path
)


def get_ffmpeg_exe() -> Optional[str]:
    """Locate FFmpeg executable from system PATH, imageio_ffmpeg, or standard installation paths."""
    exe = shutil.which("ffmpeg")
    if exe:
        return exe
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass
    for p in [r"C:\ffmpeg\bin\ffmpeg.exe", r"C:\ProgramData\chocolatey\bin\ffmpeg.exe"]:
        if os.path.isfile(p):
            return p
    return None


class HiAnimeProvider:
    """
    Provider for searching and downloading anime episodes from HiAnime (hianime.at),
    specializing in English Dubbed audio and dual sub/dub releases.
    """

    NAME = "HiAnime"
    BASE_URL = "https://hianime.at"
    XOR_KEY = b"otaku-embed-v1"

    HEADERS = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Referer": "https://hianime.at/",
        "Accept": "*/*"
    }

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update(self.HEADERS)
        adapter = requests.adapters.HTTPAdapter(
            pool_connections=64,
            pool_maxsize=64,
            max_retries=Retry(total=3, backoff_factor=0.3, status_forcelist=[500, 502, 503, 504])
        )
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)

    @staticmethod
    def extract_id(slug_or_id: str) -> str:
        """Extract clean anime ID from slug or URL string."""
        s = str(slug_or_id).strip()
        if '?' in s:
            s = s.split('?')[0]
        # Remove trailing slash
        s = s.rstrip('/')
        # If url: e.g. https://hianime.at/classroom-of-the-elite-668
        if '/' in s:
            s = s.split('/')[-1]
        # ID is usually at the end after dash: e.g. classroom-of-the-elite-668 -> 668
        m = re.search(r'-(\d+)$', s)
        if m:
            return m.group(1)
        if s.isdigit():
            return s
        return s

    def search(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """
        Search anime series on HiAnime. Returns list with sub & dub availability flags.
        """
        q_clean = clean_text(query).strip()
        if not q_clean:
            return []

        search_url = f"{self.BASE_URL}/search?keyword={urllib.parse.quote(q_clean)}"
        try:
            r = self.session.get(search_url, timeout=12)
            if r.status_code != 200 or "<title>Just a moment" in r.text:
                return []

            soup = BeautifulSoup(r.text, "html.parser")
            results = []

            for item in soup.select(".flw-item"):
                a = item.select_one("h3.film-name a")
                if not a:
                    continue

                title = clean_text(a.get("title") or a.text).strip()
                jname = clean_text(a.get("data-jname") or "").strip()
                href = a.get("href", "").strip().rstrip('/')
                slug = href.split('/')[-1]
                anime_id = self.extract_id(href)

                sub_badge = item.select_one(".tick-sub")
                dub_badge = item.select_one(".tick-dub")
                eps_badge = item.select_one(".tick-eps")

                has_sub = sub_badge is not None or eps_badge is not None
                has_dub = dub_badge is not None

                sub_count = sub_badge.text.strip() if sub_badge else ""
                dub_count = dub_badge.text.strip() if dub_badge else ""

                tags = []
                if has_dub:
                    tags.append(f"Dub: {dub_count}" if dub_count else "Dub")
                if has_sub:
                    tags.append(f"Sub: {sub_count}" if sub_count else "Sub")

                tag_label = f" [{', '.join(tags)}]" if tags else ""
                jname_part = f" ({jname})" if jname and jname.lower() != title.lower() else ""
                display_title = f"{title}{jname_part}{tag_label}"

                results.append({
                    "title": display_title,
                    "raw_title": title,
                    "jname": jname,
                    "slug": slug,
                    "anime_id": anime_id,
                    "url": f"{self.BASE_URL}/{slug}",
                    "has_dub": has_dub,
                    "has_sub": has_sub,
                    "sub_count": sub_count,
                    "dub_count": dub_count,
                    "provider": "hianime",
                    "source": "HiAnime (Dub & Sub)"
                })

                if len(results) >= limit:
                    break

            return results
        except Exception:
            return []

    def get_anime_details(self, slug_or_id: str) -> Dict[str, Any]:
        """
        Fetch anime metadata and complete episode list from HiAnime.
        """
        anime_id = self.extract_id(slug_or_id)
        slug = str(slug_or_id).strip()
        if '?' in slug:
            slug = slug.split('?')[0]
        slug = slug.rstrip('/')
        if '/' in slug:
            slug = slug.split('/')[-1]

        # 1. Fetch info page for metadata
        page_url = f"{self.BASE_URL}/{slug}" if "-" in slug else f"{self.BASE_URL}/anime-{anime_id}"
        title = slug.replace("-", " ").title()
        vintage = ""
        genres = []
        status = "Completed"
        creator = "Unknown"
        summary = ""

        try:
            r_page = self.session.get(page_url, timeout=12)
            if r_page.status_code == 200 and "<title>Just a moment" not in r_page.text:
                soup = BeautifulSoup(r_page.text, "html.parser")
                t_el = soup.select_one("h2.film-name")
                if t_el:
                    title = clean_text(t_el.text).strip()

                desc_el = soup.select_one(".film-description")
                if desc_el:
                    summary = clean_text(desc_el.text).strip()

                for item in soup.select(".anisc-info .item"):
                    item_text = clean_text(item.text).strip()
                    if item_text.startswith("Aired:"):
                        aired_str = item_text.replace("Aired:", "").strip()
                        # Extract year: e.g. Jul 12, 2017
                        y_m = re.search(r'\b(19\d\d|20\d\d)\b', aired_str)
                        if y_m:
                            vintage = y_m.group(1)
                    elif item_text.startswith("Status:"):
                        status = item_text.replace("Status:", "").strip()
                    elif item_text.startswith("Genres:"):
                        genres = [clean_text(g.text).strip() for g in item.select("a") if g.text.strip()]
                    elif item_text.startswith("Studios:"):
                        creator = item_text.replace("Studios:", "").strip()
        except Exception:
            pass

        # 2. Fetch episode listing from theme API
        ep_api_url = f"{self.BASE_URL}/api/theme/episode/list/{anime_id}"
        episodes = []
        try:
            r_ep = self.session.get(
                ep_api_url,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=12
            )
            if r_ep.status_code == 200:
                data = r_ep.json()
                html = data.get("html", "")
                ep_soup = BeautifulSoup(html, "html.parser")
                for ep in ep_soup.select(".ep-item"):
                    ep_id = ep.get("data-id")
                    num_str = ep.get("data-number", "0")
                    try:
                        num = int(num_str)
                    except ValueError:
                        try:
                            num = int(float(num_str))
                        except ValueError:
                            num = len(episodes) + 1

                    ep_title = ep.get("title") or f"Episode {num}"
                    episodes.append({
                        "number": num,
                        "id": ep_id,
                        "title": clean_text(ep_title),
                        "url": f"{self.BASE_URL}/watch/{slug}?ep={ep_id}",
                        "is_special": False
                    })
        except Exception:
            pass

        return {
            "title": title,
            "slug": slug,
            "anime_id": anime_id,
            "creator": creator,
            "status": status,
            "vintage": vintage,
            "age_group": "All Ages",
            "genres": genres,
            "summary": summary,
            "episodes": episodes,
            "total_episodes": len(episodes),
            "provider": "hianime"
        }

    def get_episode_download_sources(
        self,
        episode_id: str,
        voice_pref: str = "dub"
    ) -> List[Dict[str, Any]]:
        """
        Resolves media streaming sources for an episode in Dub or Sub mode.
        Decrypts ZokoAnime embed player and pulls direct HLS m3u8 playlists.
        """
        ep_id = str(episode_id).strip()
        servers_url = f"{self.BASE_URL}/api/theme/episode/servers?episodeId={ep_id}"

        try:
            r = self.session.get(
                servers_url,
                headers={"X-Requested-With": "XMLHttpRequest"},
                timeout=12
            )
            if r.status_code != 200:
                return []

            data = r.json()
            html = data.get("html", "")
            soup = BeautifulSoup(html, "html.parser")

            modes_to_try = []
            pref_lower = (voice_pref or "dub").lower().strip()
            if pref_lower in ("dub", "english dub"):
                modes_to_try = ["dub", "sub"]
            elif pref_lower == "dual":
                modes_to_try = ["dub", "sub"]
            else:
                modes_to_try = ["sub", "dub"]

            sources = []

            for mode in modes_to_try:
                # Find matching server items
                server_items = soup.select(f".server-item[data-type='{mode}']")
                for s in server_items:
                    s_name = s.get("data-server-name", "")
                    s_hash = s.get("data-hash", "")
                    if not s_hash:
                        continue

                    try:
                        embed_url = base64.b64decode(s_hash).decode("utf-8")
                    except Exception:
                        continue

                    if not embed_url.startswith("http"):
                        continue

                    # If ZokoAnime, deobfuscate __P blob
                    if "zokoanime" in embed_url.lower():
                        stream_info = self._extract_zoko_stream(embed_url)
                        if stream_info and stream_info.get("src"):
                            m3u8_src = stream_info["src"]
                            voice_type = "Dub" if mode == "dub" else "Sub"
                            lang_label = "English Dub" if mode == "dub" else "English Sub"
                            sources.append({
                                "filename": f"Episode_{ep_id}_{voice_type}_1080p.mp4",
                                "media_url": m3u8_src,
                                "m3u8_url": m3u8_src,
                                "voice_type": voice_type,
                                "sub_lang": "English",
                                "lang_label": lang_label,
                                "quality": "1080p",
                                "tags": ["1080p", lang_label, "HiAnime HLS"],
                                "server": s_name,
                                "ext": ".mp4"
                            })

            return sources
        except Exception:
            return []

    def _extract_zoko_stream(self, embed_url: str) -> Optional[Dict[str, Any]]:
        """Extracts and deobfuscates streaming manifest from ZokoAnime player."""
        try:
            r = self.session.get(
                embed_url,
                headers={"Referer": "https://hianime.at/"},
                timeout=12
            )
            if r.status_code != 200:
                return None

            m = re.search(r'window\.__P\s*=\s*["\']([^"\']+)["\']', r.text)
            if not m:
                return None

            raw = base64.b64decode(m.group(1))
            k_len = len(self.XOR_KEY)
            unmasked = bytes([b ^ self.XOR_KEY[i % k_len] for i, b in enumerate(raw)])
            json_str = unmasked.decode("utf-8", errors="ignore")
            data = json.loads(json_str)
            return data
        except Exception:
            return None

    def download_hls_stream(
        self,
        m3u8_url: str,
        dest_path: str,
        max_workers: int = 20,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> bool:
        """
        Concurrently downloads an HLS video stream using a high-speed continuous
        sliding-window worker pipeline and remuxes into a standard MP4 container.
        """
        temp_dest = dest_path + ".part"
        temp_ts = temp_dest + ".ts"
        base_dir = os.path.dirname(os.path.abspath(dest_path))
        os.makedirs(base_dir, exist_ok=True)

        try:
            # 1. Fetch master playlist
            r_master = self.session.get(
                m3u8_url,
                headers={"Referer": "https://zokoanime.video/"},
                timeout=12
            )
            if r_master.status_code != 200:
                return False

            lines = r_master.text.splitlines()
            target_playlist = m3u8_url

            for l in lines:
                l_str = l.strip()
                if l_str and l_str.endswith(".m3u8"):
                    if l_str.startswith("http"):
                        target_playlist = l_str
                    else:
                        base_u = m3u8_url.rsplit('/', 1)[0]
                        target_playlist = f"{base_u}/{l_str}"
                    break

            # 2. Fetch sub playlist with chunk segments
            r_sub = self.session.get(
                target_playlist,
                headers={"Referer": "https://zokoanime.video/"},
                timeout=12
            )
            if r_sub.status_code != 200:
                return False

            segments = []
            for l in r_sub.text.splitlines():
                l_str = l.strip()
                if l_str and not l_str.startswith("#"):
                    if l_str.startswith("http"):
                        segments.append(l_str)
                    else:
                        base_sub = target_playlist.rsplit('/', 1)[0]
                        segments.append(f"{base_sub}/{l_str}")

            if not segments:
                return False

            total_chunks = len(segments)
            req_headers = {
                "User-Agent": self.HEADERS["User-Agent"],
                "Referer": "https://zokoanime.video/",
                "Connection": "keep-alive"
            }

            def fetch_single_chunk(pair: Tuple[int, str]) -> Tuple[int, bytes]:
                idx, url = pair
                for attempt in range(4):
                    try:
                        r = self.session.get(url, headers=req_headers, timeout=(5, 18))
                        if r.status_code == 200 and r.content:
                            return idx, r.content
                    except Exception:
                        time.sleep(0.15 * (attempt + 1))
                return idx, b""

            # High-speed continuous sliding-window pipeline
            # Keeps max_workers saturated with zero idle barrier pauses
            window_size = max(max_workers * 2, 40)
            completed_chunks: Dict[int, bytes] = {}
            next_write_idx = 0
            cur_bytes = 0
            seg_iter = enumerate(segments)
            t_start = time.time()
            last_cb_time = 0.0

            pbar = tqdm(
                total=total_chunks,
                desc="Downloading HLS Stream",
                unit="chunk",
                leave=False
            )

            with open(temp_ts, "wb") as f_out, ThreadPoolExecutor(max_workers=max_workers) as executor:
                futures: Dict[Any, int] = {}
                # Prime the pipeline
                for _ in range(window_size):
                    try:
                        idx, seg_url = next(seg_iter)
                        fut = executor.submit(fetch_single_chunk, (idx, seg_url))
                        futures[fut] = idx
                    except StopIteration:
                        break

                while futures:
                    done, _ = wait(futures.keys(), return_when=FIRST_COMPLETED)
                    for fut in done:
                        idx = futures.pop(fut)
                        try:
                            res_idx, content = fut.result()
                            completed_chunks[res_idx] = content
                        except Exception:
                            completed_chunks[idx] = b""
                        pbar.update(1)

                        # Immediately replenish worker slot
                        try:
                            new_idx, new_url = next(seg_iter)
                            new_fut = executor.submit(fetch_single_chunk, (new_idx, new_url))
                            futures[new_fut] = new_idx
                        except StopIteration:
                            pass

                    # Write contiguous completed chunks immediately in strictly ordered sequence
                    while next_write_idx in completed_chunks:
                        chunk_bytes = completed_chunks.pop(next_write_idx)
                        if chunk_bytes:
                            f_out.write(chunk_bytes)
                            cur_bytes += len(chunk_bytes)
                        next_write_idx += 1

                    elapsed = time.time() - t_start
                    cur_mb = cur_bytes / (1024 * 1024)
                    speed_mb = cur_mb / elapsed if elapsed > 1.0 else 0.0

                    if next_write_idx > 0 and speed_mb > 0.05:
                        est_total_mb = (cur_mb / next_write_idx) * total_chunks
                        rem_mb = max(0.0, est_total_mb - cur_mb)
                        rem_sec = int(rem_mb / speed_mb)
                        eta_str = f"{rem_sec // 60}m {rem_sec % 60:02d}s"
                    else:
                        eta_str = "--:--"

                    pbar.set_postfix_str(f"{cur_mb:.1f}MB | {speed_mb:.2f}MB/s | ETA {eta_str}")

                    now = time.time()
                    if progress_callback and total_chunks > 0 and (now - last_cb_time >= 0.4 or next_write_idx == total_chunks):
                        last_cb_time = now
                        pct = round((next_write_idx / total_chunks) * 100.0, 1)
                        progress_callback({
                            "event": "download_progress",
                            "downloaded_chunks": next_write_idx,
                            "total_chunks": total_chunks,
                            "percent": pct,
                            "downloaded": cur_bytes,
                            "downloaded_mb": round(cur_mb, 1),
                            "speed_mb": round(speed_mb, 2),
                            "speed_str": f"{speed_mb:.2f} MB/s",
                            "eta_str": eta_str,
                            "total": cur_bytes,
                            "filename": os.path.basename(dest_path)
                        })

                # Flush any stragglers
                for remaining_idx in sorted(completed_chunks.keys()):
                    chunk_bytes = completed_chunks.pop(remaining_idx)
                    if chunk_bytes:
                        f_out.write(chunk_bytes)
                        cur_bytes += len(chunk_bytes)

            pbar.close()

            # Remux raw MPEG-TS chunks into standard MP4 container with clean timestamps and moov atom
            ffmpeg_exe = get_ffmpeg_exe()
            if ffmpeg_exe and os.path.exists(temp_ts) and os.path.getsize(temp_ts) > 1024 * 1024:
                remux_cmd = [
                    ffmpeg_exe, "-y", "-i", temp_ts,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    temp_dest
                ]
                try:
                    res = subprocess.run(remux_cmd, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=300)
                    if res.returncode == 0 and os.path.exists(temp_dest) and os.path.getsize(temp_dest) > 1024 * 1024:
                        if os.path.exists(temp_ts):
                            try:
                                os.remove(temp_ts)
                            except Exception:
                                pass
                        if os.path.exists(dest_path):
                            os.remove(dest_path)
                        os.rename(temp_dest, dest_path)
                        return True
                except Exception:
                    pass

            # Fallback if ffmpeg is unavailable or failed
            if os.path.exists(temp_ts) and os.path.getsize(temp_ts) > 1024 * 1024:
                if os.path.exists(dest_path):
                    os.remove(dest_path)
                os.rename(temp_ts, dest_path)
                return True
            else:
                if os.path.exists(temp_ts):
                    os.remove(temp_ts)
                return False
        except Exception:
            for stale in (temp_ts, temp_dest):
                if os.path.exists(stale):
                    try:
                        os.remove(stale)
                    except Exception:
                        pass
            return False

    def download_anime(
        self,
        slug_or_id: str,
        start_ep: int = 1,
        end_ep: Optional[int] = None,
        quality: str = "best",
        language: str = "english",
        voice_pref: str = "dub",
        strict_voice: bool = False,
        output_dir: str = "anime_files",
        overwrite: bool = False,
        delay: float = 0.5,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Batch downloader for anime series from HiAnime with full English Dub support
        and Jellyfin library structure.
        """
        details = self.get_anime_details(slug_or_id)
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
                "error": "No episodes found on HiAnime"
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
            ep_id = ep.get("id")
            is_special = ep.get("is_special", False)

            season_folder, jellyfin_fn = get_jellyfin_episode_path(
                anime_title,
                vintage,
                ep_num,
                ep_title,
                ext=".mp4",
                is_special=is_special
            )
            season_dir = os.path.join(series_dir, season_folder)
            os.makedirs(season_dir, exist_ok=True)
            dest_path = os.path.join(season_dir, jellyfin_fn)
            dest_fn = os.path.join(season_folder, jellyfin_fn)

            # Check if episode is already downloaded
            if os.path.exists(dest_path) and not overwrite and os.path.getsize(dest_path) > 1024 * 1024:
                print(f"[{idx}/{len(selected)}] {ep_title} -> [SKIP] Already exists: {dest_fn}")
                stats["skipped"] += 1
                continue

            print(f"[{idx}/{len(selected)}] Resolving {ep_title}...")

            sources = self.get_episode_download_sources(ep_id, voice_pref=voice_pref)
            if not sources:
                time.sleep(1.0)
                sources = self.get_episode_download_sources(ep_id, voice_pref=voice_pref)

            if not sources:
                print(f"  [ERROR] No media sources found on HiAnime for {ep_title}.")
                stats["failed"] += 1
                continue

            # Pick source matching voice preference
            chosen = None
            v_req = (voice_pref or "dub").lower().strip()
            if v_req == "dub":
                dubs = [s for s in sources if s.get("voice_type") == "Dub"]
                if dubs:
                    chosen = dubs[0]
                elif strict_voice:
                    print(f"  [SKIP - NO DUB] English Dub not available on HiAnime for {ep_title}.")
                    stats["skipped"] += 1
                    continue
                else:
                    chosen = sources[0]
                    print(f"  [VOICE FALLBACK] English Dub not available on HiAnime for {ep_title} -> falling back to: {chosen.get('lang_label', 'English Sub')}")
            else:
                chosen = sources[0]

            voice_tag = chosen.get("lang_label", "English Dub")
            print(f"  [DOWNLOAD] {dest_fn} [{voice_tag}] [1080p]...")

            if progress_callback:
                progress_callback({
                    "event": "episode_start",
                    "episode_num": ep_num,
                    "total_episodes": len(selected),
                    "episode_title": ep_title,
                    "filename": dest_fn,
                    "voice_tag": voice_tag
                })

            success = self.download_hls_stream(
                chosen["m3u8_url"],
                dest_path,
                max_workers=20,
                progress_callback=progress_callback
            )

            if success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024:
                size_mb = os.path.getsize(dest_path) / (1024 * 1024)
                print(f"  [OK] Saved (Jellyfin): {dest_fn} ({size_mb:.1f} MB)")
                stats["downloaded"] += 1
            else:
                print(f"  [ERROR] Failed to download {dest_fn}.")
                stats["failed"] += 1

            if delay > 0 and idx < len(selected):
                time.sleep(delay)

        return stats
