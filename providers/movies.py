"""
providers/movies.py - Dedicated Movie & Cinema Provider for Alexandria Studio.
Supports:
- HiAnime Anime Movies & Films with English Dubs, Subs, and 1080p HLS streams.
- TokyoInsider Anime Movies and OVA films.
- Internet Archive (Archive.org) Feature Films, Classic Movies, Sci-Fi, Horror, Film Noir, and Public Domain Cinema.
- Direct URL / HLS stream movie downloading with FFmpeg container repair (+faststart).
- Jellyfin-compliant movie library organization:
    Book_Files/movies/<Movie Title> (<Year>)/<Movie Title> (<Year>).mp4
Strictly 100% text-based with zero emojis.
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


def is_title_relevant(query: str, candidate_title: str) -> bool:
    """Check if candidate title contains the key substantive words of the query."""
    stop_words = {"the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for", "with", "from", "by", "movie", "film"}
    q_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', query) if w.lower() not in stop_words]
    if not q_words:
        q_words = [w.lower() for w in re.findall(r'[a-zA-Z0-9]+', query)]
    if not q_words:
        return True

    cand_lower = candidate_title.lower()
    matched = sum(1 for w in q_words if w in cand_lower)
    min_required = max(1, len(q_words) // 2 + (1 if len(q_words) % 2 != 0 else 0))
    return matched >= min_required


def sanitize_jellyfin_name(name: str, max_length: int = 120) -> str:
    """
    Sanitizes string for Jellyfin filename / folder standards.
    Removes invalid characters: \\ / : * ? " < > | while preserving readable spaces and hyphens.
    """
    if not name:
        return "Movie"
    name = name.replace('\u2013', '-').replace('\u2014', '-').replace('\u2015', '-')
    name = name.replace('\u2018', "'").replace('\u2019', "'")
    name = name.replace('\u201c', '').replace('\u201d', '')
    name = name.replace('\u00a0', ' ')
    name = name.replace(':', ' - ')
    clean = re.sub(r'[\\/*?"<>|]', '', name)
    clean = re.sub(r'\s+', ' ', clean).strip(' ._-')
    if len(clean) > max_length:
        clean = clean[:max_length].rstrip(' ._-')
    return clean or "Movie"


def get_jellyfin_movie_path(
    title: str,
    year: Optional[str] = None,
    quality: Optional[str] = None,
    ext: str = ".mp4"
) -> Tuple[str, str]:
    """
    Computes Jellyfin-compliant (movie_folder, movie_filename).
    Spec: <movie_folder>/<movie_filename>
    Example:
      title="Spirited Away", year="2001"
      -> ("Spirited Away (2001)", "Spirited Away (2001).mp4")
    """
    # Extract year from title if embedded like "Spirited Away (2001)"
    m_yr = re.search(r'\(\s*(\d{4})\s*\)', title)
    if m_yr:
        extracted_year = m_yr.group(1)
        base_title = re.sub(r'\(\s*\d{4}\s*\)', '', title).strip()
        year = year or extracted_year
    else:
        base_title = title.strip()

    # Clean base title
    clean_title = sanitize_jellyfin_name(base_title)
    if year:
        folder_name = f"{clean_title} ({year})"
    else:
        folder_name = clean_title

    ext_clean = ext if ext.startswith('.') else f".{ext}"
    filename = f"{folder_name}{ext_clean}"
    return folder_name, filename


class MovieProvider:
    """
    Unified Movie Provider for Alexandria.
    Integrates HiAnime, TokyoInsider, and Internet Archive Feature Films.
    """

    NAME = "Movies"
    ARCHIVE_API = "https://archive.org/advancedsearch.php"

    ARCHIVE_COLLECTIONS = {
        "feature_films": "Feature Films & World Cinema",
        "SciFi_Horror": "Sci-Fi & Horror Cinema Classics",
        "Film_Noir": "Film Noir & Crime Thrillers",
        "Comedy_Films": "Classic Comedy Feature Films",
        "silent_films": "Silent Era Masterpieces & Classics"
    }

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        })
        adapter = requests.adapters.HTTPAdapter(pool_connections=32, pool_maxsize=32)
        self.session.mount("https://", adapter)
        self.session.mount("http://", adapter)
        self._hianime = None
        self._tokyoinsider = None

    @property
    def hianime(self):
        if self._hianime is None:
            from .hianime import HiAnimeProvider
            self._hianime = HiAnimeProvider()
        return self._hianime

    @property
    def tokyoinsider(self):
        if self._tokyoinsider is None:
            from .tokyoinsider import TokyoInsiderProvider
            self._tokyoinsider = TokyoInsiderProvider()
        return self._tokyoinsider

    def _fetch_json(self, url: str, timeout: int = 15) -> Optional[Any]:
        try:
            resp = self.session.get(url, timeout=timeout)
            if resp.status_code == 200:
                return resp.json()
        except Exception:
            pass
        return None

    def search_movies(self, query: str, limit: int = 25, provider: str = "all") -> List[Dict[str, Any]]:
        """
        Unified movie search across HiAnime, TokyoInsider, and Archive.org Feature Films.
        """
        q = clean_text(query).strip()
        if not q:
            return []

        results = []
        seen_keys = set()

        # 1. Search HiAnime Anime Movies
        if provider in ("all", "hianime", "anime"):
            try:
                hi_results = self.hianime.search(q, limit=limit)
                for r in hi_results:
                    # Check if this item is a movie or OVA film
                    raw_title = r.get("raw_title") or r["title"]
                    is_movie = (
                        r.get("type", "").lower() in ("movie", "ova", "special") or
                        "movie" in raw_title.lower() or
                        "film" in raw_title.lower() or
                        r.get("sub_count") == 1 or
                        r.get("dub_count") == 1
                    )
                    if is_movie and is_title_relevant(q, raw_title):
                        key = re.sub(r'[^a-zA-Z0-9]', '', raw_title.lower())
                        if key not in seen_keys:
                            seen_keys.add(key)
                            # Extract year if present
                            m_y = re.search(r'\((\d{4})\)', raw_title)
                            yr = m_y.group(1) if m_y else None
                            dub_cnt = r.get("dub_count", 0)
                            sub_cnt = r.get("sub_count", 0)
                            voice_tag = "Dub & Sub" if dub_cnt and sub_cnt else ("Dub" if dub_cnt else "Sub")
                            results.append({
                                "id": r.get("slug"),
                                "slug": r.get("slug"),
                                "title": raw_title,
                                "clean_title": clean_text(re.sub(r'\[.*?\]|\(.*?\)', '', raw_title)).strip(),
                                "year": yr,
                                "provider": "hianime",
                                "media_type": "movie",
                                "voice_tag": voice_tag,
                                "rating": r.get("rating", "N/A"),
                                "quality": "1080p",
                                "url": f"https://hianime.to/{r.get('slug')}"
                            })
            except Exception:
                pass

        # 2. Search TokyoInsider Anime Movies
        if provider in ("all", "tokyoinsider", "anime"):
            try:
                ti_results = self.tokyoinsider.search(q, limit=limit)
                for r in ti_results:
                    raw_title = r.get("title", "")
                    if ("(movie" in raw_title.lower() or "(film" in raw_title.lower() or "movie" in q.lower()) and is_title_relevant(q, raw_title):
                        key = re.sub(r'[^a-zA-Z0-9]', '', raw_title.lower())
                        if key not in seen_keys:
                            seen_keys.add(key)
                            m_y = re.search(r'\((\d{4})\)', raw_title)
                            yr = m_y.group(1) if m_y else r.get("vintage")
                            results.append({
                                "id": r.get("slug"),
                                "slug": r.get("slug"),
                                "title": raw_title,
                                "clean_title": clean_text(re.sub(r'\[.*?\]|\(.*?\)', '', raw_title)).strip(),
                                "year": str(yr) if yr else None,
                                "provider": "tokyoinsider",
                                "media_type": "movie",
                                "voice_tag": "Sub",
                                "rating": "N/A",
                                "quality": "720p/1080p",
                                "url": f"https://www.tokyoinsider.com/anime/{r.get('letter', 'A')}/{r.get('slug')}"
                            })
            except Exception:
                pass

        # 3. Search Internet Archive Feature Films & Classic Movies
        if provider in ("all", "archive", "cinema", "classics"):
            try:
                words = [w.strip() for w in q.split() if w.strip()]
                if words:
                    and_query = " AND ".join(f'title:({w})' for w in words)
                    search_query = f'(mediatype:(movies) OR collection:(feature_films) OR collection:(classic_movies)) AND ({and_query})'
                    params = {
                        "q": search_query,
                        "fl[]": ["identifier", "title", "description", "year", "downloads", "runtime"],
                        "sort[]": "downloads desc",
                        "rows": limit,
                        "output": "json"
                    }
                    url = f"{self.ARCHIVE_API}?{requests.compat.urlencode(params, doseq=True)}"
                    data = self._fetch_json(url, timeout=15)
                    docs = data.get("response", {}).get("docs", []) if data else []

                    # Fallback broad search if strict title yielded zero hits
                    if not docs:
                        params["q"] = f'(mediatype:(movies) OR collection:(feature_films)) AND ({q})'
                        url = f"{self.ARCHIVE_API}?{requests.compat.urlencode(params, doseq=True)}"
                        data2 = self._fetch_json(url, timeout=15)
                        docs = data2.get("response", {}).get("docs", []) if data2 else []

                    # Prioritize full movies over trailers
                    def doc_sort_key(d):
                        t = (d.get("title") or "").lower()
                        is_trailer = "trailer" in t or "preview" in t
                        return (1 if is_trailer else 0, -int(d.get("downloads", 0)))

                    docs.sort(key=doc_sort_key)

                    for d in docs:
                        ident = d.get("identifier")
                        if not ident:
                            continue
                        title = clean_text(d.get("title") or ident)
                        if not is_title_relevant(q, title):
                            continue
                        key = re.sub(r'[^a-zA-Z0-9]', '', title.lower())
                        if key not in seen_keys:
                            seen_keys.add(key)
                            desc = clean_text(re.sub(r'<[^>]+>', ' ', d.get("description") or "")).strip()
                            yr = d.get("year")
                            dls = d.get("downloads", 0)
                            runtime = d.get("runtime")

                            results.append({
                                "id": ident,
                                "identifier": ident,
                                "title": title,
                                "clean_title": title,
                                "year": str(yr) if yr else None,
                                "provider": "archive_movie",
                                "media_type": "movie",
                                "voice_tag": "Original",
                                "downloads": dls,
                                "runtime": runtime,
                                "summary": desc[:220] + ("..." if len(desc) > 220 else ""),
                                "quality": "1080p/720p Direct MP4",
                                "url": f"https://archive.org/details/{ident}"
                            })
            except Exception:
                pass

        return results[:limit]

    def browse_archive_movies(self, collection: str = "feature_films", limit: int = 25) -> List[Dict[str, Any]]:
        """
        Browse top-rated and most downloaded classic feature films on Internet Archive.
        """
        col_tag = collection if collection in self.ARCHIVE_COLLECTIONS else "feature_films"
        search_query = f'collection:({col_tag}) AND mediatype:(movies)'
        params = {
            "q": search_query,
            "fl[]": ["identifier", "title", "description", "year", "downloads", "runtime"],
            "sort[]": "downloads desc",
            "rows": limit,
            "output": "json"
        }
        url = f"{self.ARCHIVE_API}?{requests.compat.urlencode(params, doseq=True)}"
        data = self._fetch_json(url, timeout=15)
        if not data or not isinstance(data, dict):
            return []

        docs = data.get("response", {}).get("docs", [])
        results = []
        for d in docs:
            ident = d.get("identifier")
            if not ident:
                continue
            title = clean_text(d.get("title") or ident)
            desc = clean_text(re.sub(r'<[^>]+>', ' ', d.get("description") or "")).strip()
            yr = d.get("year")
            dls = d.get("downloads", 0)
            runtime = d.get("runtime")

            results.append({
                "id": ident,
                "identifier": ident,
                "title": title,
                "year": str(yr) if yr else None,
                "collection": col_tag,
                "collection_title": self.ARCHIVE_COLLECTIONS.get(col_tag, "Feature Films"),
                "downloads": dls,
                "runtime": runtime,
                "summary": desc[:250] + ("..." if len(desc) > 250 else ""),
                "provider": "archive_movie",
                "media_type": "movie"
            })
        return results

    def get_archive_movie_files(self, identifier: str) -> List[Dict[str, Any]]:
        """
        Fetches direct MP4 video files for an Internet Archive movie, sorted by best resolution.
        """
        url = f"https://archive.org/metadata/{identifier}"
        data = self._fetch_json(url, timeout=18)
        if not data or not isinstance(data, dict):
            return []

        files = data.get("files", [])
        server = data.get("server") or "ia600000.us.archive.org"
        d1 = data.get("dir") or ""
        mp4s = []

        for f in files:
            name = f.get("name", "")
            fmt = f.get("format", "")
            if name.lower().endswith(".mp4") or "mp4" in fmt.lower() or "h.264" in fmt.lower():
                sz_bytes = int(f.get("size", 0))
                # Skip tiny video samples < 5MB
                if sz_bytes < 5 * 1024 * 1024:
                    continue

                # Determine resolution rank
                fn_lower = name.lower()
                if "1080p" in fn_lower:
                    rank = 1080
                    res_tag = "1080p Full HD"
                elif "720p" in fn_lower:
                    rank = 720
                    res_tag = "720p HD"
                elif "dvd" in fn_lower:
                    rank = 576
                    res_tag = "DVD High-Quality"
                elif "512kb" in fn_lower:
                    rank = 360
                    res_tag = "360p Standard"
                else:
                    rank = 480
                    res_tag = "480p SD / MP4"

                sz_mb = sz_bytes / (1024 * 1024)
                sz_str = f"{sz_mb / 1024:.2f} GB" if sz_mb >= 1024 else f"{sz_mb:.1f} MB"

                direct_url = f"https://archive.org/download/{identifier}/{name}"
                mp4s.append({
                    "name": name,
                    "resolution": res_tag,
                    "rank": rank,
                    "size_bytes": sz_bytes,
                    "size_str": sz_str,
                    "url": direct_url,
                    "format": fmt
                })

        # Sort descending by resolution rank, then size
        mp4s.sort(key=lambda x: (x["rank"], x["size_bytes"]), reverse=True)
        return mp4s

    def download_movie(
        self,
        movie_target: Any,
        quality: str = "best",
        voice_pref: str = "dub",
        strict_voice: bool = False,
        output_dir: str = "book_files",
        overwrite: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """
        Download a movie from HiAnime, Archive.org, TokyoInsider, or Direct URL,
        format into Jellyfin Movie standard, and repair container with FFmpeg (+faststart).
        """
        # Determine provider and identifiers
        provider = "archive_movie"
        identifier = None
        title = "Movie"
        year = None

        if isinstance(movie_target, dict):
            provider = movie_target.get("provider", "archive_movie")
            identifier = movie_target.get("identifier") or movie_target.get("id") or movie_target.get("slug")
            title = movie_target.get("title") or title
            year = movie_target.get("year")
        else:
            input_str = str(movie_target).strip()
            if "archive.org/details/" in input_str:
                provider = "archive_movie"
                m = re.search(r'archive\.org/details/([^/\?#]+)', input_str)
                identifier = m.group(1) if m else input_str
            elif "hianime.to" in input_str or "hianime.at" in input_str:
                provider = "hianime"
                identifier = input_str
            elif "tokyoinsider.com" in input_str:
                provider = "tokyoinsider"
                identifier = input_str
            elif input_str.startswith("http"):
                provider = "direct_url"
                identifier = input_str
            else:
                provider = "archive_movie"
                identifier = input_str

        # Jellyfin Movie Directory Structure: <output_dir>/movies/<Movie Title> (<Year>)/<Movie Title> (<Year>).mp4
        # If output_dir is already a movies library or contains an existing Movies folder, resolve intelligently
        base_name = os.path.basename(os.path.normpath(output_dir)).lower()
        if base_name in ["movies", "movie", "films", "film", "cinema"]:
            movies_root = output_dir
        else:
            try:
                import config
                movies_root = config.get_media_dir("movie", output_dir)
            except Exception:
                movies_root = os.path.join(output_dir, "movies")
        os.makedirs(movies_root, exist_ok=True)

        movie_folder, movie_fn = get_jellyfin_movie_path(title, year=year, quality=quality, ext=".mp4")
        target_dir = os.path.join(movies_root, movie_folder)
        os.makedirs(target_dir, exist_ok=True)
        dest_path = os.path.join(target_dir, movie_fn)

        if os.path.exists(dest_path) and not overwrite and os.path.getsize(dest_path) > 1024 * 1024:
            print(f"\n[*] Movie already downloaded: {dest_path} ({os.path.getsize(dest_path) / (1024*1024):.1f} MB)")
            return {
                "success": True,
                "title": title,
                "folder": target_dir,
                "file": dest_path,
                "skipped": True
            }

        print(f"\n========================================================================")
        print(f"  Downloading Movie: {movie_folder}")
        print(f"  Destination:       {dest_path}")
        print(f"  Provider:          {provider.upper()}")
        print(f"========================================================================\n")

        # Provider 1: HiAnime (HLS stream download with sliding window + remux)
        if provider == "hianime":
            details = self.hianime.get_anime_details(identifier)
            episodes = details.get("episodes", [])
            if not episodes:
                print("No movie streams found on HiAnime.")
                return {"success": False, "error": "No streams found"}

            ep = episodes[0]
            ep_id = ep.get("id")
            sources = self.hianime.get_episode_download_sources(ep_id, voice_pref=voice_pref)
            if not sources:
                print("Failed to acquire stream sources from HiAnime.")
                return {"success": False, "error": "Source extraction failed"}

            chosen = sources[0]
            if voice_pref == "dub":
                dubs = [s for s in sources if s.get("voice_type") == "Dub"]
                if dubs:
                    chosen = dubs[0]

            print(f"Streaming HLS playlist [{chosen.get('voice_type', 'Sub')} - 1080p]...")
            success = self.hianime.download_hls_stream(
                chosen["m3u8_url"],
                dest_path,
                max_workers=20,
                progress_callback=progress_callback
            )

        # Provider 2: TokyoInsider (stream decoder)
        elif provider == "tokyoinsider":
            details = self.tokyoinsider.get_anime_details(identifier)
            episodes = details.get("episodes", [])
            if not episodes:
                print("No movie episodes found on TokyoInsider.")
                return {"success": False, "error": "No episodes found"}

            ep = episodes[0]
            options = self.tokyoinsider.get_download_options(ep)
            if not options:
                print("Failed to resolve download mirrors on TokyoInsider.")
                return {"success": False, "error": "Mirror lookup failed"}

            chosen = options[0]
            print(f"Downloading stream from TokyoInsider ({chosen.get('quality', 'HD')})...")
            success = self._download_http_stream(chosen["url"], dest_path)

        # Provider 3: Internet Archive (direct HTTP download with resume and progress bar)
        elif provider == "archive_movie":
            files = self.get_archive_movie_files(identifier)
            if not files:
                print(f"No direct MP4 movie files found for item '{identifier}'.")
                return {"success": False, "error": "No MP4 files"}

            # Pick best resolution matching quality preference
            chosen_file = files[0]
            if quality in ("720p", "480p", "360p"):
                matched = [f for f in files if quality in f["resolution"].lower()]
                if matched:
                    chosen_file = matched[0]

            print(f"Selected Media File: {chosen_file['name']}")
            print(f"Quality:             {chosen_file['resolution']}")
            print(f"File Size:           {chosen_file['size_str']}")
            print(f"Download URL:        {chosen_file['url']}\n")

            success = self._download_http_stream(chosen_file["url"], dest_path)

        # Provider 4: Direct URL
        else:
            print(f"Downloading from direct video URL: {identifier}...")
            success = self._download_http_stream(identifier, dest_path)

        # Post-download verification and FFmpeg container repair
        if success and os.path.exists(dest_path) and os.path.getsize(dest_path) > 1024 * 1024:
            self._ensure_faststart_mp4(dest_path)
            size_mb = os.path.getsize(dest_path) / (1024 * 1024)
            print(f"\n[OK] Movie download complete: {movie_fn} ({size_mb:.1f} MB)")

            # Record in library progress
            try:
                import progress
                progress.save_watch_progress(
                    target_dir,
                    dest_path,
                    episode_title=movie_folder,
                    total_episodes=1,
                    episode_index=1,
                    media_type="movie",
                    mark_completed=False,
                    status="unwatched"
                )
            except Exception:
                pass

            return {
                "success": True,
                "title": title,
                "folder": target_dir,
                "file": dest_path
            }
        else:
            print(f"\n[ERROR] Movie download failed or output file is corrupted.")
            return {"success": False, "error": "Download failed"}

    def _download_http_stream(self, url: str, dest_path: str) -> bool:
        """
        High-throughput multi-chunk HTTP stream downloader with real-time throughput display,
        automatic resume, and rolling ETA.
        """
        part_path = dest_path + ".part"
        resume_byte = 0
        if os.path.exists(part_path):
            resume_byte = os.path.getsize(part_path)

        headers = {}
        if resume_byte > 0:
            headers["Range"] = f"bytes={resume_byte}-"

        try:
            resp = self.session.get(url, headers=headers, stream=True, timeout=30)
            if resp.status_code not in (200, 206):
                # Try without range header if server rejected range
                if resume_byte > 0:
                    resume_byte = 0
                    resp = self.session.get(url, stream=True, timeout=30)
                if resp.status_code not in (200, 206):
                    print(f"HTTP Error {resp.status_code} while downloading.")
                    return False

            total_size = int(resp.headers.get("content-length", 0)) + resume_byte
            mode = "ab" if resume_byte > 0 else "wb"

            chunk_size = 1024 * 1024  # 1MB buffer
            t_start = time.time()
            downloaded = resume_byte

            with open(part_path, mode) as f, tqdm(
                total=total_size,
                initial=resume_byte,
                unit="B",
                unit_scale=True,
                unit_divisor=1024,
                desc="Downloading",
                bar_format="{desc}: {percentage:3.0f}%|{bar}| {n_fmt}/{total_fmt} [{rate_fmt}{postfix}]"
            ) as pbar:
                for chunk in resp.iter_content(chunk_size=chunk_size):
                    if chunk:
                        f.write(chunk)
                        downloaded += len(chunk)
                        pbar.update(len(chunk))

            if os.path.exists(dest_path):
                os.remove(dest_path)
            os.rename(part_path, dest_path)
            return True

        except Exception as e:
            print(f"Download stream error: {e}")
            return False

    def _ensure_faststart_mp4(self, file_path: str):
        """
        Ensure MP4 has ISOBMFF faststart atom placement so desktop players
        open the video instantly without seeking latency.
        """
        try:
            from .hianime import get_ffmpeg_exe
            ffmpeg = get_ffmpeg_exe()
            if not ffmpeg or not os.path.isfile(file_path):
                return

            with open(file_path, "rb") as f:
                header = f.read(32)

            # If it doesn't have proper ISOBMFF ftyp header, remux it
            if not header.startswith(b"\x00\x00\x00") or b"ftyp" not in header[:16]:
                tmp_out = file_path + ".remux.mp4"
                print("  [REMUX] Finalizing ISOBMFF MP4 container with +faststart...")
                import subprocess
                cmd = [
                    ffmpeg, "-y",
                    "-i", file_path,
                    "-c", "copy",
                    "-movflags", "+faststart",
                    tmp_out
                ]
                proc = subprocess.run(cmd, capture_output=True, timeout=120)
                if proc.returncode == 0 and os.path.isfile(tmp_out) and os.path.getsize(tmp_out) > 1024 * 1024:
                    os.replace(tmp_out, file_path)
                    print("  [OK] Remux verified and finalized.")
                else:
                    if os.path.isfile(tmp_out):
                        os.remove(tmp_out)
        except Exception:
            pass


ARCHIVE_COLLECTIONS = MovieProvider.ARCHIVE_COLLECTIONS
