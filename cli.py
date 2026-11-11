import sys
import os
import re
import json
import time
import textwrap
import argparse
import subprocess
from typing import Optional, List, Dict, Any, Tuple

from scraper import MediaScraper
import progress

# Ensure UTF-8 output on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass

def print_banner():
    banner = r"""
========================================================================
    _    _     _______  __    _    _   _ ____  ____  ___    _    
   / \  | |   | ____\ \/ /   / \  | \ | |  _ \|  _ \|_ _|  / \   
  / _ \ | |   |  _|  \  /   / _ \ |  \| | | | | |_) || |  / _ \  
 / ___ \| |___| |___ /  \  / ___ \| |\  | |_| |  _ < | | / ___ \ 
/_/   \_\_____|_____/_/\_\/_/   \_\_| \_|____/|_| \_\___/_/   \_\
            Universal Media Archive & Studio
========================================================================
"""
    print(banner)

def prompt_choice(prompt_text: str, valid_choices: List[str]) -> str:
    while True:
        choice = input(prompt_text).strip()
        if choice in valid_choices:
            return choice
        display_choices = [c for c in valid_choices if c]
        print(f"Invalid input. Please choose from: {', '.join(display_choices)}")

def prompt_int(prompt_text: str, default: Optional[int] = None, min_val: int = 1, max_val: Optional[int] = None) -> int:
    while True:
        suffix = f" [{default}]" if default is not None else ""
        raw = input(f"{prompt_text}{suffix}: ").strip()
        if not raw and default is not None:
            return default
        try:
            val = int(raw)
            if val < min_val:
                print(f"Value must be >= {min_val}")
                continue
            if max_val is not None and val > max_val:
                print(f"Value must be <= {max_val}")
                continue
            return val
        except ValueError:
            print("Please enter a valid integer.")

def sanitize_filename(name: str, max_length: int = 80) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', '', name).strip()
    return cleaned[:max_length].strip()

def get_video_duration(file_path: str) -> Optional[float]:
    """Retrieve video duration in seconds using FFmpeg if available."""
    try:
        from providers.hianime import get_ffmpeg_exe
        ffmpeg = get_ffmpeg_exe()
        if not ffmpeg or not os.path.isfile(file_path):
            return None
        res = subprocess.run([ffmpeg, "-i", file_path], capture_output=True, text=True, timeout=5)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", res.stderr)
        if m:
            h, m_val, s = int(m.group(1)), int(m.group(2)), float(m.group(3))
            return h * 3600.0 + m_val * 60.0 + s
    except Exception:
        pass
    return None

def _parse_timestamp_input(ts_str: str, duration_sec: Optional[float] = None) -> Optional[float]:
    """Parse user timestamp strings like '15:30', '1:12:00', '45%', '720s'."""
    s = ts_str.strip().lower()
    if not s:
        return None
    if s.endswith("%"):
        try:
            pct = float(s[:-1].strip())
            if duration_sec:
                return (pct / 100.0) * duration_sec
        except Exception:
            return None
    if s.endswith("s"):
        s = s[:-1].strip()
    if ":" in s:
        parts = s.split(":")
        try:
            if len(parts) == 2:
                return int(parts[0]) * 60.0 + float(parts[1])
            elif len(parts) == 3:
                return int(parts[0]) * 3600.0 + int(parts[1]) * 60.0 + float(parts[2])
        except Exception:
            return None
    try:
        return float(s)
    except Exception:
        return None

def play_video_file(file_path: str, series_dir: Optional[str] = None):
    """Play video using native system media player."""
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    # Automatically identify series directory if not explicitly provided
    if not series_dir:
        parent = os.path.dirname(os.path.abspath(file_path))
        if os.path.basename(parent).lower().startswith("season"):
            series_dir = os.path.dirname(parent)
        else:
            series_dir = parent

    print(f"\nLaunching video player for:\n  {file_path}\n")
    if sys.platform == "win32":
        try:
            os.startfile(file_path)
            return
        except Exception:
            pass
    import subprocess
    try:
        if sys.platform == "darwin":
            subprocess.Popen(["open", file_path])
        else:
            subprocess.Popen(["xdg-open", file_path])
    except Exception as e:
        print(f"Failed to open video player: {e}")

def get_anime_directories(scraper: MediaScraper) -> List[str]:
    """Returns valid anime directory roots, checking configured Jellyfin and legacy folders."""
    import config
    paths = config.resolve_jellyfin_paths(scraper.output_dir)
    resolved = paths["anime"]
    candidates = [resolved]
    if paths.get("is_dedicated_library") and paths.get("dedicated_type") == "anime":
        candidates.append(scraper.output_dir)
    else:
        for sub in ["anime", "Anime"]:
            p = os.path.join(scraper.output_dir, sub)
            candidates.append(p)
    candidates.append("anime_files")

    seen = set()
    existing = []
    for c in candidates:
        if c and os.path.isdir(c):
            norm = os.path.normcase(os.path.abspath(c))
            if norm not in seen:
                seen.add(norm)
                existing.append(c)
    return existing if existing else [resolved]

def get_anime_series_folder(scraper: MediaScraper, title: str, vintage: str = "") -> str:
    """Finds existing anime series folder (checking Jellyfin and legacy naming) or returns default target location."""
    from providers.tokyoinsider import get_jellyfin_series_folder_name
    jellyfin_title = get_jellyfin_series_folder_name(title, vintage)
    legacy_title = sanitize_filename(title, max_length=60)
    for root in get_anime_directories(scraper):
        # 1. Check Jellyfin name
        candidate_jelly = os.path.join(root, jellyfin_title)
        if os.path.isdir(candidate_jelly):
            return candidate_jelly
        # 2. Check legacy name
        candidate_legacy = os.path.join(root, legacy_title)
        if os.path.isdir(candidate_legacy):
            return candidate_legacy
        # 3. Fuzzy match by base title
        clean_base = re.sub(r'\s*\((?:TV|Movie|OVA)\s*\d*\)\s*', '', title, flags=re.I).strip().lower()
        if os.path.isdir(root):
            for d in os.listdir(root):
                dp = os.path.join(root, d)
                if os.path.isdir(dp) and clean_base in d.lower():
                    return dp
    primary = get_anime_directories(scraper)[0]
    return os.path.join(primary, jellyfin_title)

def get_tv_directories(scraper: MediaScraper) -> List[str]:
    """Returns valid TV series directory roots, checking configured Jellyfin and legacy folders."""
    import config
    paths = config.resolve_jellyfin_paths(scraper.output_dir)
    resolved = paths["tv"]
    candidates = [resolved]
    if paths.get("is_dedicated_library") and paths.get("dedicated_type") == "tv":
        candidates.append(scraper.output_dir)
    else:
        for sub in ["tv", "TV", "TV Shows", "tv shows", "shows", "Shows"]:
            p = os.path.join(scraper.output_dir, sub)
            candidates.append(p)
    candidates.extend(["tv_files", "shows"])

    seen = set()
    existing = []
    for c in candidates:
        if c and os.path.isdir(c):
            norm = os.path.normcase(os.path.abspath(c))
            if norm not in seen:
                seen.add(norm)
                existing.append(c)
    return existing if existing else [resolved]

def get_tv_series_folder(scraper: MediaScraper, title: str, year: Optional[str] = None) -> str:
    """Finds existing TV series folder or returns default target Jellyfin location."""
    from providers.tvshows import sanitize_jellyfin_name
    clean_title = sanitize_jellyfin_name(title)
    folder_name = f"{clean_title} ({year})" if year else clean_title
    for root in get_tv_directories(scraper):
        candidate = os.path.join(root, folder_name)
        if os.path.isdir(candidate):
            return candidate
        if os.path.isdir(root):
            for d in os.listdir(root):
                dp = os.path.join(root, d)
                if os.path.isdir(dp) and clean_title.lower() in d.lower():
                    return dp
    primary = get_tv_directories(scraper)[0]
    return os.path.join(primary, folder_name)


def get_movie_directories(scraper: MediaScraper) -> List[str]:
    """Returns valid movie directory roots, checking configured Jellyfin and legacy folders."""
    import config
    paths = config.resolve_jellyfin_paths(scraper.output_dir)
    resolved = paths["movie"]
    candidates = [resolved]
    if paths.get("is_dedicated_library") and paths.get("dedicated_type") == "movie":
        candidates.append(scraper.output_dir)
    else:
        for sub in ["movies", "Movies", "films", "Films"]:
            p = os.path.join(scraper.output_dir, sub)
            candidates.append(p)
    candidates.extend(["movie_files", "movies"])

    seen = set()
    existing = []
    for c in candidates:
        if c and os.path.isdir(c):
            norm = os.path.normcase(os.path.abspath(c))
            if norm not in seen:
                seen.add(norm)
                existing.append(c)
    return existing if existing else [resolved]

def get_movie_folder(scraper: MediaScraper, title: str, year: Optional[str] = None) -> str:
    """Finds existing movie folder or returns default target Jellyfin location."""
    from providers.movies import get_jellyfin_movie_path
    folder_name, _ = get_jellyfin_movie_path(title, year=year)
    for root in get_movie_directories(scraper):
        candidate = os.path.join(root, folder_name)
        if os.path.isdir(candidate):
            return candidate
        clean_base = re.sub(r'\(.*?\)', '', title).strip().lower()
        if os.path.isdir(root):
            for d in os.listdir(root):
                dp = os.path.join(root, d)
                if os.path.isdir(dp) and clean_base in d.lower():
                    return dp
    primary = get_movie_directories(scraper)[0]
    return os.path.join(primary, folder_name)

def _display_anime_episodes(episodes: List[Dict[str, Any]]):
    if not episodes:
        print("No episodes found.")
        return
    page_size = 25
    offset = 0
    while True:
        chunk = episodes[offset:offset + page_size]
        print(f"\nEpisodes ({offset + 1} to {min(len(episodes), offset + page_size)} of {len(episodes)}):")
        print("-" * 75)
        for ep in chunk:
            print(f"  [#{ep.get('number'):3d}] {ep.get('title')}")
        print("-" * 75)
        print("Commands: [N]ext page | [P]rev page | [Enter] to return")
        cmd = input("Choice: ").strip().lower()
        if cmd == "n":
            if offset + page_size < len(episodes):
                offset += page_size
            else:
                print("Already on the last page.")
        elif cmd == "p":
            if offset >= page_size:
                offset -= page_size
            else:
                print("Already on the first page.")
        else:
            return

def _play_episode_from_folder(folder_path: str):
    if not os.path.isdir(folder_path):
        print(f"Folder not found: {folder_path}")
        return

    video_items = []
    for root, dirs, files in os.walk(folder_path):
        dirs.sort()
        for f in sorted(files):
            if f.endswith(".part"):
                continue
            if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                full = os.path.join(root, f)
                try:
                    if os.path.getsize(full) > 1024 * 512:
                        rel = os.path.relpath(full, folder_path)
                        video_items.append((rel, full))
                except OSError:
                    pass

    if not video_items:
        print(f"No video files (.mp4, .mkv, .avi) found in '{folder_path}'.")
        return

    def video_sort_key(item):
        rel, full = item
        rel_lower = rel.lower()
        m_se = re.search(r's(\d+)e(\d+)', rel_lower)
        if m_se:
            return (int(m_se.group(1)), int(m_se.group(2)), rel_lower)
        m_ep = re.search(r'episode[_\s]+(\d+)', rel_lower)
        if m_ep:
            return (1, int(m_ep.group(1)), rel_lower)
        m_num = re.search(r'(?:^|[\\/])(\d{1,3})[\s\.\-_]', rel_lower)
        if m_num:
            return (1, int(m_num.group(1)), rel_lower)
        return (99, 9999, rel_lower)

    video_items.sort(key=video_sort_key)
    series_name = os.path.basename(folder_path)
    media_type = "anime" if "anime" in folder_path.lower() else ("tv" if "tv" in folder_path.lower() else "video")

    def _is_ep_watched(rel: str, full: str, watched_list: List[str]) -> bool:
        norm_rel = rel.replace("/", "\\").lower()
        fn = os.path.basename(full).lower()
        for w in watched_list:
            norm_w = w.replace("/", "\\").lower()
            if norm_rel == norm_w or fn == os.path.basename(norm_w).lower():
                return True
        return False

    while True:
        watched_list = progress.get_watched_episodes(folder_path)
        watched_count = sum(1 for rel, full in video_items if _is_ep_watched(rel, full, watched_list))
        pct = (watched_count / max(1, len(video_items))) * 100.0

        w_info = progress.get_watch_progress(folder_path)
        last_played_idx = None
        if w_info:
            last_file = w_info.get("episode_file") or w_info.get("rel_path") or ""
            for i, (rel, full) in enumerate(video_items, 1):
                if _is_ep_watched(rel, full, [last_file]):
                    last_played_idx = i
                    break

        # Find next episode: prefer sequential episode after last watched, else first unwatched
        next_unwatched_idx = None
        if last_played_idx and last_played_idx < len(video_items):
            for i in range(last_played_idx + 1, len(video_items) + 1):
                rel, full = video_items[i - 1]
                if not _is_ep_watched(rel, full, watched_list):
                    next_unwatched_idx = i
                    break

        if next_unwatched_idx is None:
            for i, (rel, full) in enumerate(video_items, 1):
                if not _is_ep_watched(rel, full, watched_list):
                    next_unwatched_idx = i
                    break

        if next_unwatched_idx is None:
            next_unwatched_idx = last_played_idx or 1

        last_title = ""
        if w_info:
            last_title = w_info.get("episode_title") or w_info.get("rel_path") or ""
            if len(last_title) > 36:
                last_title = "..." + last_title[-33:]

        print(f"\n{'=' * 75}")
        print(f"  {series_name} [Episodes & Watch History]")
        last_str = f" | Last Watched: {last_title}" if last_title else ""
        print(f"  Watched: {watched_count} of {len(video_items)} episodes ({pct:.1f}%){last_str}")
        print(f"{'=' * 75}")

        all_ep_details = progress.get_all_episodes_detail(folder_path)

        for idx, (rel, full) in enumerate(video_items, 1):
            sz_mb = os.path.getsize(full) / (1024 * 1024)
            is_w = _is_ep_watched(rel, full, watched_list)
            norm_rel = rel.replace("/", "\\")
            ep_d = all_ep_details.get(norm_rel)
            if not ep_d:
                ep_d = progress.get_episode_detail(folder_path, rel)

            if is_w or (ep_d and ep_d.get("status") == "completed"):
                dur_str = f" ({progress.format_seconds(ep_d.get('duration_sec', 0))})" if (ep_d and ep_d.get('duration_sec')) else ""
                status_tag = f"[Watched{dur_str}]"
            elif ep_d and ep_d.get("status") == "in_progress" and ep_d.get("position_sec"):
                pos_str = progress.format_seconds(ep_d.get("position_sec", 0))
                dur_str = progress.format_seconds(ep_d.get("duration_sec", 0)) if ep_d.get("duration_sec") else "?"
                pct_str = f"{ep_d.get('percent', 0):.0f}%"
                status_tag = f"[{pos_str}/{dur_str} {pct_str}]"
            elif idx == next_unwatched_idx:
                status_tag = "[Next Up]"
            else:
                status_tag = "[       ]"
            print(f"  [{idx:2d}] {status_tag} {rel} ({sz_mb:.1f} MB)")

        print("-" * 75)
        next_ep_name = video_items[next_unwatched_idx - 1][0]
        if len(next_ep_name) > 30:
            next_ep_name = "..." + next_ep_name[-27:]
        print("Commands:")
        print(f"  [Enter / R] Resume Next Episode (Episode {next_unwatched_idx}: {next_ep_name})")
        print(f"  [1-{len(video_items)}]       Play selected episode")
        print("  [T]         Set custom watch timestamp / resume position")
        print("  [M]         Mark episode as Watched / Unwatched")
        print("  [A]         Mark all episodes as Watched")
        print("  [C]         Clear watch history (Reset)")
        print("  [0]         Back to menu")

        cmd = input(f"\nChoice [Enter, 1-{len(video_items)}, T, M, A, C, 0]: ").strip().lower()

        if cmd in ("", "r"):
            target_idx = next_unwatched_idx
        elif cmd == "0":
            return
        elif cmd == "t":
            t_idx = prompt_int(f"Enter episode number to set timestamp [1-{len(video_items)}] or [0] to cancel", min_val=0, max_val=len(video_items))
            if t_idx > 0:
                t_rel, t_full = video_items[t_idx - 1]
                t_dur = get_video_duration(t_full)
                dur_hint = f" (Total: {progress.format_seconds(t_dur)})" if t_dur else ""
                ts_in = input(f"Enter timestamp for Episode {t_idx} (e.g. '14:30', '75%', 'done', '0'){dur_hint}: ").strip().lower()
                if ts_in in ("done", "100%", "watched", "complete"):
                    progress.save_watch_progress(
                        folder_path,
                        t_full,
                        episode_title=t_rel,
                        total_episodes=len(video_items),
                        episode_index=t_idx,
                        media_type=media_type,
                        mark_completed=True,
                        position_sec=t_dur,
                        duration_sec=t_dur,
                        status="completed"
                    )
                    print(f"\n[*] Marked Episode {t_idx} as Completed (100%).")
                elif ts_in in ("0", "reset", "unwatched"):
                    progress.mark_episode_watched(folder_path, t_rel, watched=False, total_episodes=len(video_items))
                    print(f"\n[*] Reset Episode {t_idx} to Unwatched.")
                elif ts_in:
                    parsed_pos = _parse_timestamp_input(ts_in, t_dur)
                    if parsed_pos is not None:
                        progress.save_watch_progress(
                            folder_path,
                            t_full,
                            episode_title=t_rel,
                            total_episodes=len(video_items),
                            episode_index=t_idx,
                            media_type=media_type,
                            mark_completed=False,
                            position_sec=parsed_pos,
                            duration_sec=t_dur,
                            status="in_progress"
                        )
                        pct_s = f" ({min(100.0, round((parsed_pos / t_dur) * 100.0, 1))}%)" if t_dur else ""
                        print(f"\n[*] Saved resume position for Episode {t_idx} at {progress.format_seconds(parsed_pos)}{pct_s}.")
                    else:
                        print("\n[!] Unrecognized timestamp format.")
            continue
        elif cmd == "m":
            m_idx = prompt_int(f"Enter episode number to toggle watched status [1-{len(video_items)}] or [0] to cancel", min_val=0, max_val=len(video_items))
            if m_idx > 0:
                t_rel, t_full = video_items[m_idx - 1]
                cur_w = _is_ep_watched(t_rel, t_full, watched_list)
                progress.mark_episode_watched(folder_path, t_rel, watched=not cur_w, total_episodes=len(video_items))
                status_word = "UNWATCHED" if cur_w else "WATCHED"
                print(f"\n[*] Marked Episode {m_idx} as {status_word}.")
            continue
        elif cmd == "a":
            progress.mark_all_episodes_watched(folder_path, [full for _, full in video_items], watched=True)
            print("\n[*] Marked all episodes as WATCHED.")
            continue
        elif cmd == "c":
            progress.mark_all_episodes_watched(folder_path, [full for _, full in video_items], watched=False)
            print("\n[*] Cleared watch history for this series.")
            continue
        elif cmd.isdigit() and 1 <= int(cmd) <= len(video_items):
            target_idx = int(cmd)
        else:
            print(f"Invalid choice '{cmd}'.")
            continue

        # Play loop starting from target_idx
        current_play_idx = target_idx
        while current_play_idx <= len(video_items):
            selected_rel, selected_full = video_items[current_play_idx - 1]
            dur_sec = get_video_duration(selected_full)
            dur_str = progress.format_seconds(dur_sec) if dur_sec else "Unknown"

            print(f"\n{'=' * 75}")
            print(f"  Now Playing: {selected_rel}")
            print(f"  Duration:    {dur_str}")
            print(f"  Status:      Player launching in background...")
            print(f"{'=' * 75}\n")

            t_start = time.time()
            play_video_file(selected_full, series_dir=folder_path)

            print(f"[*] Player active. Watching session started.")
            print(f"[*] Press [Enter] when done watching (or enter resume timestamp like '14:20' or 'done'):")
            session_input = input(">> ").strip().lower()
            elapsed_sec = time.time() - t_start

            if session_input in ("done", "watched", "complete", "100%"):
                progress.save_watch_progress(
                    folder_path,
                    selected_full,
                    episode_title=selected_rel,
                    total_episodes=len(video_items),
                    episode_index=current_play_idx,
                    media_type=media_type,
                    mark_completed=True,
                    position_sec=dur_sec,
                    duration_sec=dur_sec,
                    status="completed"
                )
                print(f"\n[*] Marked Episode {current_play_idx} as Completed (100%).")
            elif session_input in ("0", "reset", "unwatched"):
                progress.mark_episode_watched(folder_path, selected_rel, watched=False, total_episodes=len(video_items))
                print(f"\n[*] Marked Episode {current_play_idx} as Unwatched.")
            elif session_input:
                manual_pos = _parse_timestamp_input(session_input, dur_sec)
                if manual_pos is not None:
                    progress.save_watch_progress(
                        folder_path,
                        selected_full,
                        episode_title=selected_rel,
                        total_episodes=len(video_items),
                        episode_index=current_play_idx,
                        media_type=media_type,
                        mark_completed=False,
                        position_sec=manual_pos,
                        duration_sec=dur_sec,
                        status="in_progress"
                    )
                    pct_val = min(100.0, round((manual_pos / dur_sec) * 100.0, 1)) if dur_sec else 0.0
                    print(f"\n[*] Saved resume position at {progress.format_seconds(manual_pos)} ({pct_val:.1f}%).")
                else:
                    print(f"\n[!] Unrecognized input format. Keeping current progress.")
            else:
                # User pressed Enter with no text
                if dur_sec and elapsed_sec >= 0.85 * dur_sec:
                    progress.save_watch_progress(
                        folder_path,
                        selected_full,
                        episode_title=selected_rel,
                        total_episodes=len(video_items),
                        episode_index=current_play_idx,
                        media_type=media_type,
                        mark_completed=True,
                        position_sec=dur_sec,
                        duration_sec=dur_sec,
                        status="completed"
                    )
                    print(f"\n[*] Session duration: {progress.format_seconds(elapsed_sec)} (>= 85% of runtime). Automatically marked as Completed.")
                elif elapsed_sec >= 45.0:
                    pct_val = min(100.0, round((elapsed_sec / dur_sec) * 100.0, 1)) if dur_sec else 0.0
                    print(f"\n[*] Session ended after {progress.format_seconds(elapsed_sec)} ({pct_val:.1f}% of episode).")
                    print("  [1] Save resume position [Default]")
                    print("  [2] Mark episode as Fully Watched (100%)")
                    print("  [3] Keep as Unwatched")
                    post_act = prompt_choice("Choose action [1, 2, 3] [1]: ", ["1", "2", "3", ""])
                    if post_act in ("1", ""):
                        progress.save_watch_progress(
                            folder_path,
                            selected_full,
                            episode_title=selected_rel,
                            total_episodes=len(video_items),
                            episode_index=current_play_idx,
                            media_type=media_type,
                            mark_completed=False,
                            position_sec=elapsed_sec,
                            duration_sec=dur_sec,
                            status="in_progress"
                        )
                        print(f"[*] Saved resume position at {progress.format_seconds(elapsed_sec)}.")
                    elif post_act == "2":
                        progress.save_watch_progress(
                            folder_path,
                            selected_full,
                            episode_title=selected_rel,
                            total_episodes=len(video_items),
                            episode_index=current_play_idx,
                            media_type=media_type,
                            mark_completed=True,
                            position_sec=dur_sec,
                            duration_sec=dur_sec,
                            status="completed"
                        )
                        print(f"[*] Marked Episode {current_play_idx} as Completed.")
                    else:
                        print(f"[*] Kept Episode {current_play_idx} as Unwatched.")
                else:
                    print(f"\n[*] Playback session closed quickly ({progress.format_seconds(elapsed_sec)}). Watch status unchanged.")

            new_watched = progress.get_watched_episodes(folder_path)
            new_cnt = sum(1 for r, f in video_items if _is_ep_watched(r, f, new_watched))
            new_pct = (new_cnt / max(1, len(video_items))) * 100.0
            print(f"[*] Library progress: {new_cnt}/{len(video_items)} episodes completed ({new_pct:.1f}%).")

            if current_play_idx < len(video_items):
                next_rel = video_items[current_play_idx][0]
                post_ans = prompt_choice(f"\nPlay Next Episode [{current_play_idx + 1}] ({next_rel}) now? (y/n) [n]: ", ["y", "n", ""])
                if post_ans == "y":
                    current_play_idx += 1
                    continue
            else:
                print("\n[*] You have reached the last downloaded episode of this series!")
            break


def _download_range_dialog(scraper: MediaScraper, details: Dict[str, Any], total_episodes: int, series_folder: str):
    if total_episodes == 0:
        print("No episodes available for download.")
        return

    start_ep = prompt_int("Start episode", default=1, min_val=1, max_val=max(1, total_episodes))
    end_ep = prompt_int("End episode", default=total_episodes, min_val=start_ep, max_val=max(start_ep, total_episodes))

    print("\nAudio & Voice Preference:")
    print("  [1] Subbed (Japanese Audio with Subtitles) [Default]")
    print("  [2] Dubbed (English Voice Acting)")
    print("  [3] Dual Audio (Includes both English Dub + Japanese Audio)")
    print("  [4] Any / No Preference")
    v_choice = prompt_choice("Choose audio preference [1, 2, 3, 4] [1]: ", ["1", "2", "3", "4", ""])
    v_map = {"1": "sub", "2": "dub", "3": "dual", "4": "any", "": "sub"}
    voice_pref = v_map.get(v_choice, "sub")

    strict_voice = False
    if voice_pref in ("dub", "dual"):
        label = "English Dub" if voice_pref == "dub" else "Dual Audio"
        prov_name = "HiAnime" if details.get("provider") == "hianime" else "TokyoInsider"
        print(f"\nIf {label} is not available on {prov_name} for an episode:")
        print("  [1] Automatically fall back to English Sub [Default]")
        print(f"  [2] Skip episode if {label} is unavailable")
        fb_choice = prompt_choice("Choose fallback option [1, 2] [1]: ", ["1", "2", ""])
        strict_voice = (fb_choice == "2")

    print("\nSubtitle / Language Preference:")
    print("  [1] English Subtitles [Default]")
    print("  [2] Custom Language (e.g. Spanish, French, German, Arabic, Italian, Portuguese)")
    print("  [3] Any / No Language Filter")
    l_choice = prompt_choice("Choose language preference [1, 2, 3] [1]: ", ["1", "2", "3", ""])
    if l_choice == "2":
        custom_lang = input("Enter language name (e.g. Spanish, French, Arabic): ").strip().lower()
        language = custom_lang if custom_lang else "english"
    elif l_choice == "3":
        language = "any"
    else:
        language = "english"

    print("\nQuality Preference:")
    print("  [1] Best Available (Highest resolution & audio)")
    print("  [2] 1080p Full HD")
    print("  [3] 720p HD")
    print("  [4] 480p / Standard Definition (Fast download & smaller file size)")
    q_choice = prompt_choice("Choose quality [1, 2, 3, 4] [1]: ", ["1", "2", "3", "4", ""])
    q_map = {"1": "best", "2": "1080p", "3": "720p", "4": "480p", "": "best"}
    quality = q_map.get(q_choice, "best")

    overwrite_ans = prompt_choice("Overwrite existing downloaded episodes? (y/n) [n]: ", ["y", "n", ""])
    overwrite = overwrite_ans.lower() == "y"

    src_name = "HiAnime" if details.get("provider") == "hianime" else "TokyoInsider"
    print(f"\nStarting {src_name} download for '{details.get('title')}' (Episodes {start_ep} to {end_ep})...")
    print(f"Preferences: Voice: {voice_pref.upper()} | Language: {language.title()} | Quality: {quality.upper()}")
    print(f"Destination: {os.path.abspath(series_folder)}")
    print("-" * 65)

    stats = scraper.download_anime(
        details.get("slug") or details.get("url"),
        start_ep=start_ep,
        end_ep=end_ep,
        quality=quality,
        language=language,
        voice_pref=voice_pref,
        strict_voice=strict_voice,
        output_dir=os.path.dirname(series_folder),
        overwrite=overwrite,
        provider=details.get("provider", "auto")
    )

    print("-" * 65)
    print(f"Download complete: {stats['downloaded']} episodes downloaded, {stats['skipped']} skipped, {stats['failed']} failed.")
    print(f"Saved in: {os.path.abspath(stats['series_folder'])}")

    if stats["downloaded"] > 0 or stats["skipped"] > 0:
        ans = prompt_choice("\nPlay first downloaded episode now? (y/n) [y]: ", ["y", "n", ""])
        if ans.lower() in ("y", ""):
            _play_episode_from_folder(stats["series_folder"])

def _download_single_episode_dialog(scraper: MediaScraper, details: Dict[str, Any], series_folder: str):
    episodes = details.get("episodes", [])
    if not episodes:
        print("No episodes found.")
        return

    ep_num = prompt_int("Enter episode number to inspect / download", default=1, min_val=1)
    chosen_ep = None
    for ep in episodes:
        if ep.get("number") == ep_num:
            chosen_ep = ep
            break
    if not chosen_ep:
        print(f"Episode {ep_num} not found in this anime's episode list.")
        return

    provider = details.get("provider", "tokyoinsider")
    src_name = "HiAnime" if provider == "hianime" else "TokyoInsider"
    print(f"\nFetching available video sources for '{chosen_ep.get('title')}' from {src_name}...")
    if provider == "hianime":
        sources = scraper.providers.hianime.get_episode_download_sources(chosen_ep.get("id") or chosen_ep.get("number"))
    else:
        sources = scraper.providers.tokyoinsider.get_episode_download_sources(chosen_ep["url"])

    if not sources:
        print("No media sources found for this episode.")
        return

    print(f"\nAvailable Video Sources for {chosen_ep.get('title')}:")
    print("-" * 75)
    for idx, s in enumerate(sources, 1):
        tags_str = f" [{', '.join(s['tags'])}]" if s.get('tags') else ""
        size_str = f" ({s['size_str']})" if s.get('size_str') else ""
        dls_str = f" - {s['downloads']} downloads" if s.get('downloads') else ""
        print(f"  [{idx:2d}] {s['filename']}{size_str}{tags_str}{dls_str}")
    print("-" * 75)

    s_idx = prompt_int(f"Choose source to download [1-{len(sources)}] or [0] to cancel", min_val=0, max_val=len(sources))
    if s_idx == 0:
        return

    selected_source = sources[s_idx - 1]
    from providers.tokyoinsider import get_jellyfin_episode_path
    anime_title = details.get("title") or "Anime"
    vintage = details.get("vintage", "")
    is_special = chosen_ep.get("is_special", False)
    season_folder, jellyfin_fn = get_jellyfin_episode_path(
        anime_title,
        vintage,
        ep_num,
        chosen_ep.get("title", f"Episode {ep_num}"),
        ext=selected_source.get("ext", ".mp4"),
        is_special=is_special
    )
    season_dir = os.path.join(series_folder, season_folder)
    os.makedirs(season_dir, exist_ok=True)
    dest_path = os.path.join(season_dir, jellyfin_fn)

    print(f"\nDownloading {jellyfin_fn}...")
    if provider == "hianime":
        success = scraper.providers.hianime.download_hls_stream(
            selected_source["m3u8_url"],
            dest_path
        )
    else:
        success = scraper.providers.tokyoinsider.download_file(
            selected_source["media_url"],
            dest_path,
            overwrite=True
        )

    if success:
        print(f"Successfully downloaded to: {dest_path}")
        play_ans = prompt_choice("\nPlay downloaded video now in video player? (y/n) [y]: ", ["y", "n", ""])
        if play_ans.lower() in ("y", ""):
            play_video_file(dest_path)
    else:
        print(f"Download failed for {jellyfin_fn}.")

def prompt_and_download_anime(scraper: MediaScraper, target: Any):
    letter = "A"
    slug = None
    provider = "auto"
    if isinstance(target, dict):
        slug = target.get('slug')
        letter = target.get('letter', 'A')
        provider = target.get('provider', 'auto')
    else:
        target_str = str(target).strip()
        if "hianime" in target_str or (re.search(r'-(\d+)$', target_str.rstrip('/')) and "/" not in target_str.strip('/\\')):
            provider = "hianime"
            slug = target_str.rstrip('/').split('/')[-1]
        else:
            letter, slug = scraper.providers.tokyoinsider.extract_slug(target_str)

    src_name = "HiAnime" if provider == "hianime" else "TokyoInsider"
    print(f"\nFetching details for Anime '{slug}' from {src_name}...")
    try:
        details = scraper.get_anime_details(slug, provider=provider)
    except Exception as e:
        print(f"Error fetching {src_name} anime details: {e}")
        return

    if not details.get("provider"):
        details["provider"] = provider

    title = details.get('title') or slug.replace('_', ' ').replace('-', ' ').title()
    creator = details.get('creator') or "Unknown"
    status = details.get('status') or "Unknown"
    vintage = details.get('vintage') or "Unknown"
    age_group = details.get('age_group') or "Unknown"
    genres = details.get('genres', [])
    episodes = details.get('episodes', [])
    total_episodes = len(episodes)
    source_label = details.get('source') or f"{src_name} (High-Res Video / Direct Media Stream)"

    print("\n" + "=" * 70)
    print(f"  Title:    {title}")
    print(f"  Creator:  {creator}")
    print(f"  Source:   {source_label}")
    print("  Type:     Anime Series (High-Res Video / Direct Media Stream)")
    print(f"  Status:   {status} | Vintage: {vintage} | Age: {age_group}")
    print(f"  Genres:   {', '.join(genres) if genres else 'N/A'}")
    print(f"  Episodes: {total_episodes}")

    syn = details.get('summary', '')
    if syn:
        from providers.tokyoinsider import clean_text
        clean_syn = clean_text(syn)
        print("\n  Description / Synopsis:")
        print("  " + "-" * 66)
        for line in textwrap.wrap(clean_syn, width=66):
            print(f"  {line}")
        print("  " + "-" * 66)
    print("=" * 70)

    series_folder = get_anime_series_folder(scraper, title, vintage=vintage)
    existing_videos = []
    if os.path.exists(series_folder):
        for root, _, files in os.walk(series_folder):
            for f in files:
                if f.endswith(".part"):
                    continue
                if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                    fp = os.path.join(root, f)
                    try:
                        if os.path.getsize(fp) > 1024 * 512:
                            existing_videos.append(fp)
                    except OSError:
                        pass

    if existing_videos:
        print(f"\n[*] Anime already has {len(existing_videos)} episode(s) downloaded in '{series_folder}'.")

    print("\nOptions:")
    print("  [1] Download episode range (e.g. Ep 1 to 25 or ALL)")
    print("  [2] Select single episode & inspect available qualities / sources")
    print("  [3] List all episodes")
    valid_opts = ["1", "2", "3", "0"]
    if existing_videos:
        print("  [4] Watch / Play downloaded episode in Video Player")
        valid_opts.append("4")
    print("  [0] Return to Previous Menu")

    opt = prompt_choice(f"Choice [{', '.join(valid_opts)}]: ", valid_opts)

    if opt == "0":
        return
    elif opt == "4" and existing_videos:
        _play_episode_from_folder(series_folder)
    elif opt == "3":
        _display_anime_episodes(episodes)
        prompt_and_download_anime(scraper, target)
    elif opt == "2":
        _download_single_episode_dialog(scraper, details, series_folder)
    elif opt == "1":
        _download_range_dialog(scraper, details, total_episodes, series_folder)

def _prompt_anime_browse_filter(current_cat: str, current_letter: Optional[str]) -> Tuple[str, Optional[str]]:
    print("\nSelect Anime Section or Letter:")
    print("-" * 65)
    print("  [1] Most Popular Anime")
    print("  [2] New Releases & Seasonal")
    print("  [3] Full Anime List (A-Z)")
    print("  [4] Browse by Alphabetical Letter (A, B, C... Z, 0-9)")
    print("  [0] Keep Current Settings")
    print("-" * 65)
    c = prompt_choice("Choice [1, 2, 3, 4, 0]: ", ["1", "2", "3", "4", "0"])

    if c == "1":
        return "popular", None
    elif c == "2":
        return "new", None
    elif c == "3":
        return "list", None
    elif c == "4":
        let = input("Enter letter (A-Z or 0-9): ").strip().upper()
        if let:
            return "list", let[0]
        return current_cat, current_letter
    return current_cat, current_letter

def interactive_browse_anime(
    scraper: MediaScraper,
    initial_category: str = "popular",
    initial_letter: Optional[str] = None
):
    current_category = initial_category or "popular"
    current_letter = initial_letter
    current_page = 1
    page_limit = 20

    category_labels = {
        "popular": "Most Popular Anime",
        "new": "New Releases & Seasonal Anime",
        "list": "Full Anime Directory (A-Z)"
    }

    while True:
        cat_display = f"Letter '{current_letter}'" if current_letter else category_labels.get(current_category, current_category.title())

        total_count = scraper.get_anime_browse_count(
            category=current_category,
            letter=current_letter
        )
        total_pages = max(1, (total_count + page_limit - 1) // page_limit)
        if current_page > total_pages:
            current_page = total_pages

        print("\n" + "=" * 75)
        print("  Anime Series Browser [TokyoInsider]")
        print(f"  Section: {cat_display} | Page: {current_page} of {total_pages} ({total_count} series)")
        print("=" * 75)
        print(f"Loading anime series ({cat_display}, Page {current_page} of {total_pages})...")

        try:
            items = scraper.browse_anime(
                category=current_category,
                letter=current_letter,
                page_num=current_page,
                limit=page_limit
            )
        except Exception as e:
            print(f"Error fetching anime from TokyoInsider: {e}")
            items = []

        if not items:
            print(f"\nNo anime series found on Page {current_page} in {cat_display}.")
            print("-" * 75)
            print("Options:")
            if current_page > 1:
                print("  [P] Previous Page")
            print("  [F] Change Section / Filter by Letter")
            print("  [0] Return to Anime Studio")
            cmd = input("Choice: ").strip().lower()
            if cmd == "p" and current_page > 1:
                current_page -= 1
                continue
            elif cmd == "f":
                new_cat, new_let = _prompt_anime_browse_filter(current_category, current_letter)
                current_category = new_cat
                current_letter = new_let
                current_page = 1
                continue
            else:
                return

        print("-" * 75)
        offset_start = (current_page - 1) * page_limit
        for idx, r in enumerate(items, 1):
            let = f"[{r.get('letter')}]" if r.get('letter') else ""
            global_num = offset_start + idx
            print(f"  [{idx:2d}] (#{global_num:3d}) {let:<4} {r['title']}")
        print("-" * 75)

        print("Commands:")
        print(f"  [1-{len(items)}] Inspect anime details, episodes & download")
        print("  [N]ext page | [P]rev page | [F]ilter / Change Section | [0] Back to Menu")
        cmd = input("Choice: ").strip().lower()

        if cmd in ("0", "b", "back", "exit", "q"):
            return
        elif cmd == "n":
            if current_page < total_pages:
                current_page += 1
            else:
                print(f"Already on the last page ({total_pages}).")
        elif cmd == "p":
            if current_page > 1:
                current_page -= 1
            else:
                print("Already on the first page.")
        elif cmd == "f":
            new_cat, new_let = _prompt_anime_browse_filter(current_category, current_letter)
            current_category = new_cat
            current_letter = new_let
            current_page = 1
        elif cmd.isdigit():
            idx = int(cmd)
            if 1 <= idx <= len(items):
                selected = items[idx - 1]
                prompt_and_download_anime(scraper, selected)
            else:
                print(f"Invalid selection: please enter 1-{len(items)}.")
        else:
            print("Invalid command. Please enter a number, [N], [P], [F], or [0].")

def interactive_play_anime(scraper: MediaScraper):
    roots = get_anime_directories(scraper)
    valid_series = []
    seen_paths = set()
    for anime_root in roots:
        if not os.path.isdir(anime_root):
            continue
        series_dirs = [d for d in os.listdir(anime_root) if os.path.isdir(os.path.join(anime_root, d))]
        for d in series_dirs:
            p = os.path.join(anime_root, d)
            if p in seen_paths:
                continue
            seen_paths.add(p)
            vids = []
            for r_dir, _, files in os.walk(p):
                for f in files:
                    if f.endswith(".part"):
                        continue
                    if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                        fp = os.path.join(r_dir, f)
                        try:
                            if os.path.getsize(fp) > 1024 * 512:
                                vids.append(fp)
                        except OSError:
                            pass
            if vids:
                last_p = progress.get_watch_progress(p)
                watched_eps = progress.get_watched_episodes(p)
                valid_series.append({
                    "title": d,
                    "path": p,
                    "video_count": len(vids),
                    "progress": last_p,
                    "watched_count": len(watched_eps),
                    "last_updated": (last_p.get("timestamp") or "") if last_p else ""
                })

    if not valid_series:
        primary_root = roots[0] if roots else "anime_files"
        print(f"\nNo downloaded anime episodes found in '{primary_root}'.")
        print("Download an anime first using Option [2] Anime Studio!")
        return

    # Sort valid series so the most recently watched anime is at the top
    valid_series.sort(key=lambda s: s.get("last_updated") or "", reverse=True)

    print("\nSelect Anime Series to Watch [Jellyfin Structure]:")
    print("-" * 75)
    for idx, s in enumerate(valid_series, 1):
        prog_str = ""
        w = s["progress"]
        tot = s["video_count"]
        w_cnt = s["watched_count"]
        pct = round((w_cnt / max(1, tot)) * 100.0, 1)
        if w:
            last_ep = w.get("episode_title") or w.get("rel_path") or ""
            if len(last_ep) > 28:
                last_ep = "..." + last_ep[-25:]
            prog_str = f" [Watched: {w_cnt}/{tot} ({pct}%) | Last: {last_ep}]"
        elif w_cnt > 0:
            prog_str = f" [Watched: {w_cnt}/{tot} ({pct}%)]"
        print(f"  [{idx:2d}] {s['title']} ({s['video_count']} episode(s)){prog_str}")
    print("-" * 75)

    s_idx = prompt_int(f"Choose anime series [1-{len(valid_series)}] or [0] to cancel", min_val=0, max_val=len(valid_series))
    if s_idx == 0:
        return
    chosen = valid_series[s_idx - 1]
    _play_episode_from_folder(chosen["path"])

def interactive_anime_studio(scraper: MediaScraper):
    while True:
        print("\n--- [ Anime Studio (HiAnime English Dubs & TokyoInsider Subs) ] ---")
        print("  [1] Search Anime (Multi-Source: HiAnime English Dubs & TokyoInsider Fansubs)")
        print("  [2] Search & Browse HiAnime (Dedicated English Dubs & 1080p HLS Streams)")
        print("  [3] Browse TokyoInsider (Most Popular, New Releases, A-Z Directory)")
        print("  [4] Watch / Play Downloaded Anime Episode (Desktop Video Player)")
        print("  [5] Download by Anime URL or Slug (HiAnime or TokyoInsider)")
        print("  [0] Back to Main Menu")
        opt = prompt_choice("Choice [1, 2, 3, 4, 5, 0]: ", ["1", "2", "3", "4", "5", "0"])

        if opt == "0":
            if hasattr(scraper.providers, "_tokyoinsider") and scraper.providers._tokyoinsider is not None:
                scraper.providers._tokyoinsider.close_browser()
            return
        elif opt in ("1", "2"):
            provider_filter = "hianime" if opt == "2" else "all"
            src_desc = "HiAnime (English Dubs & Subs)" if opt == "2" else "HiAnime & TokyoInsider"
            query = input(f"\nEnter anime title or keyword [{src_desc}]: ").strip()
            if not query:
                continue

            print(f"\nSearching {src_desc} for '{query}'...")
            results = scraper.search_anime(query, limit=25, provider=provider_filter)
            if not results:
                print(f"No anime series found matching '{query}'.")
                continue

            while True:
                print(f"\nFound {len(results)} Anime Series for '{query}':")
                print("-" * 75)
                for idx, r in enumerate(results, 1):
                    p_badge = "[HiAnime]" if r.get("provider") == "hianime" else f"[{r.get('letter', 'TI')}]"
                    print(f"  [{idx:2d}] {p_badge:<11} {r['title']}")
                print("-" * 75)

                choice = prompt_int(f"Choose anime to inspect / download [1-{len(results)}] or [0] to return", min_val=0, max_val=len(results))
                if choice == 0:
                    break

                selected = results[choice - 1]
                prompt_and_download_anime(scraper, selected)
        elif opt == "3":
            interactive_browse_anime(scraper)
        elif opt == "4":
            interactive_play_anime(scraper)
        elif opt == "5":
            url_or_slug = input("\nEnter Anime URL or slug (HiAnime or TokyoInsider): ").strip()
            if url_or_slug:
                prompt_and_download_anime(scraper, url_or_slug)

def interactive_play_tv(scraper: MediaScraper):
    roots = get_tv_directories(scraper)
    valid_series = []
    seen_paths = set()
    for tv_root in roots:
        if not os.path.isdir(tv_root):
            continue
        series_dirs = [d for d in os.listdir(tv_root) if os.path.isdir(os.path.join(tv_root, d))]
        for d in series_dirs:
            p = os.path.join(tv_root, d)
            if p in seen_paths:
                continue
            seen_paths.add(p)
            vids = []
            for r_dir, _, files in os.walk(p):
                for f in files:
                    if f.endswith(".part"):
                        continue
                    if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                        fp = os.path.join(r_dir, f)
                        try:
                            if os.path.getsize(fp) > 1024 * 512:
                                vids.append(fp)
                        except OSError:
                            pass
            if vids:
                last_p = progress.get_watch_progress(p)
                watched_eps = progress.get_watched_episodes(p)
                valid_series.append({
                    "title": d,
                    "path": p,
                    "video_count": len(vids),
                    "progress": last_p,
                    "watched_count": len(watched_eps),
                    "last_updated": (last_p.get("timestamp") or "") if last_p else ""
                })

    if not valid_series:
        primary_root = roots[0] if roots else "tv_files"
        print(f"\nNo downloaded TV show episodes found in '{primary_root}'.")
        print("Download a TV show episode first using Option [3] TV Shows Studio!")
        return

    # Sort valid series so the most recently watched TV show is at the top
    valid_series.sort(key=lambda s: s.get("last_updated") or "", reverse=True)

    print("\nSelect TV Show to Watch [Jellyfin Structure]:")
    print("-" * 75)
    for idx, s in enumerate(valid_series, 1):
        prog_str = ""
        w = s["progress"]
        tot = s["video_count"]
        w_cnt = s["watched_count"]
        pct = round((w_cnt / max(1, tot)) * 100.0, 1)
        if w:
            last_ep = w.get("episode_title") or w.get("rel_path") or ""
            if len(last_ep) > 28:
                last_ep = "..." + last_ep[-25:]
            prog_str = f" [Watched: {w_cnt}/{tot} ({pct}%) | Last: {last_ep}]"
        elif w_cnt > 0:
            prog_str = f" [Watched: {w_cnt}/{tot} ({pct}%)]"
        print(f"  [{idx:2d}] {s['title']} ({s['video_count']} episode(s)){prog_str}")
    print("-" * 75)

    s_idx = prompt_int(f"Choose TV show [1-{len(valid_series)}] or [0] to cancel", min_val=0, max_val=len(valid_series))
    if s_idx == 0:
        return
    chosen = valid_series[s_idx - 1]
    _play_episode_from_folder(chosen["path"])

def _browse_tv_episodes(title: str, year: Optional[str], episodes: List[Dict[str, Any]]):
    if not episodes:
        print("No episode guide available for this show.")
        return

    seasons_map: Dict[int, List[Dict[str, Any]]] = {}
    for ep in episodes:
        s = ep.get("season", 1)
        seasons_map.setdefault(s, []).append(ep)

    sorted_seasons = sorted(seasons_map.keys())
    print(f"\n{title} - Select Season to View:")
    print("-" * 55)
    for s_num in sorted_seasons:
        count = len(seasons_map[s_num])
        print(f"  [Season {s_num:02d}] {count} episode(s)")
    print("-" * 55)

    chosen_season = prompt_int("Enter Season Number [or 0 to cancel]", min_val=0, max_val=max(sorted_seasons))
    if chosen_season == 0 or chosen_season not in seasons_map:
        return

    season_eps = seasons_map[chosen_season]
    page_size = 20
    offset = 0
    while True:
        chunk = season_eps[offset:offset + page_size]
        print(f"\n{title} - Season {chosen_season:02d} (Episodes {offset + 1} to {min(len(season_eps), offset + page_size)} of {len(season_eps)}):")
        print("-" * 75)
        for ep in chunk:
            s_tag = f"S{ep.get('season', 1):02d}E{ep.get('number', 1):02d}"
            air = f" (Aired: {ep.get('airdate')})" if ep.get('airdate') else ""
            print(f"  [{s_tag}] {ep.get('title')}{air}")
        print("-" * 75)
        print("Commands: [N]ext page | [P]rev page | [Enter] to return")
        cmd = input("Choice: ").strip().lower()
        if cmd == "n":
            if offset + page_size < len(season_eps):
                offset += page_size
            else:
                print("Already on the last page.")
        elif cmd == "p":
            if offset >= page_size:
                offset -= page_size
            else:
                print("Already on the first page.")
        else:
            return

def _download_tv_url_dialog(scraper: MediaScraper, title: str, year: Optional[str], episodes: List[Dict[str, Any]]):
    print(f"\nDownload TV Episode for '{title}' [Direct Stream URL -> Jellyfin Format]")
    print("-" * 75)
    season_num = prompt_int("Enter Season Number", default=1, min_val=0)
    ep_num = prompt_int("Enter Episode Number", default=1, min_val=1)

    default_ep_title = ""
    for ep in episodes:
        if ep.get("season") == season_num and ep.get("number") == ep_num:
            default_ep_title = ep.get("title", "")
            break

    if default_ep_title:
        print(f"Detected Episode Title from Guide: '{default_ep_title}'")
        custom_name = input(f"Episode title [{default_ep_title}]: ").strip()
        ep_title = custom_name if custom_name else default_ep_title
    else:
        ep_title = input(f"Episode title [Episode {ep_num}]: ").strip()
        if not ep_title:
            ep_title = f"Episode {ep_num}"

    media_url = input("Enter direct video download URL (.mp4, .mkv, or stream link): ").strip()
    if not media_url:
        print("No URL entered. Aborting download.")
        return

    print(f"\nDownloading S{season_num:02d}E{ep_num:02d} directly into Jellyfin directory structure...")
    success, saved_rel = scraper.download_tv_episode(
        show_title=title,
        year=year,
        season_num=season_num,
        ep_num=ep_num,
        ep_title=ep_title,
        media_url=media_url
    )

    if success:
        print("\nSuccessfully downloaded and formatted for Jellyfin:")
        print(f"Saved: {saved_rel}")
        play_ans = prompt_choice("\nPlay downloaded episode now in video player? (y/n) [y]: ", ["y", "n", ""])
        if play_ans.lower() in ("y", ""):
            for root in get_tv_directories(scraper):
                cand = os.path.join(root, saved_rel)
                if os.path.exists(cand):
                    play_video_file(cand)
                    break
    else:
        print(f"Download failed for {title} S{season_num:02d}E{ep_num:02d}.")

def _archive_tv_search_dialog(scraper: MediaScraper, default_query: Optional[str] = None):
    if default_query:
        query = default_query
        print(f"\nSearching Internet Archive for classic TV shows matching '{query}'...")
    else:
        query = input("\nEnter classic TV show title to search on Internet Archive: ").strip()
        if not query:
            return

    results = scraper.search_archive_tv(query, limit=12)
    if not results:
        print(f"No classic TV entries found on Internet Archive for '{query}'.")
        return

    while True:
        print(f"\nFound {len(results)} Classic TV Collections / Episodes on Internet Archive:")
        print("-" * 75)
        for idx, r in enumerate(results, 1):
            yr = f" ({r['year']})" if r.get('year') else ""
            print(f"  [{idx:2d}] {r['title']}{yr}")
        print("-" * 75)

        choice = prompt_int(f"Select entry to view MP4 files [1-{len(results)}] or [0] to return", min_val=0, max_val=len(results))
        if choice == 0:
            break

        selected = results[choice - 1]
        ident = selected["identifier"]
        print(f"\nFetching available MP4 video files for '{selected['title']}'...")
        mp4s = scraper.providers.tvshows.get_archive_mp4_files(ident)
        if not mp4s:
            print("No direct MP4 video files found for this Archive entry.")
            continue

        print(f"\nAvailable MP4 Episodes / Files in '{selected['title']}':")
        print("-" * 75)
        for f_idx, f in enumerate(mp4s, 1):
            print(f"  [{f_idx:2d}] {f['filename']} ({f['size_mb']:.1f} MB)")
        print("-" * 75)

        f_choice = prompt_int(f"Select file to download in Jellyfin format [1-{len(mp4s)}] or [0] to return", min_val=0, max_val=len(mp4s))
        if f_choice == 0:
            continue

        chosen_file = mp4s[f_choice - 1]
        raw_fn = chosen_file["filename"]

        # Parse season and episode number from filename
        m_se = re.search(r's(\d+)e(\d+)', raw_fn, re.I)
        m_x = re.search(r'(\d+)\s*x\s*(\d+)', raw_fn, re.I)
        m_ep = re.search(r'(?:ep(?:isode)?|part)[\s_.-]*(\d+)', raw_fn, re.I)
        m_lead = re.match(r'^\s*0*(\d+)\b', raw_fn)

        if m_se:
            detected_season = int(m_se.group(1))
            detected_ep = int(m_se.group(2))
        elif m_x:
            detected_season = int(m_x.group(1))
            detected_ep = int(m_x.group(2))
        elif m_ep:
            detected_season = 1
            detected_ep = int(m_ep.group(1))
        elif m_lead:
            detected_season = 1
            detected_ep = int(m_lead.group(1))
        else:
            detected_season = 1
            detected_ep = f_choice

        clean_ep_title = os.path.splitext(raw_fn)[0]
        clean_ep_title = re.sub(r'^[sS]\d+[eE]\d+[\s_.-]*', '', clean_ep_title)
        clean_ep_title = re.sub(r'^\d+\s*x\s*\d+[\s_.-]*', '', clean_ep_title, flags=re.I)
        clean_ep_title = re.sub(r'^(?:ep(?:isode)?|part)[\s_.-]*\d+[\s_.-]*', '', clean_ep_title, flags=re.I)
        clean_ep_title = re.sub(r'^\d+[\s_.-]+', '', clean_ep_title)
        clean_ep_title = re.sub(r'[\(\[]\s*\d{3,4}p[^\)\]]*[\)\]]', '', clean_ep_title, flags=re.I).strip(' ._-')
        if not clean_ep_title:
            clean_ep_title = f"Episode {detected_ep}"

        print(f"\nTarget File: {raw_fn}")
        season_num = prompt_int("Season Number", default=detected_season, min_val=0)
        ep_num = prompt_int("Episode Number", default=detected_ep, min_val=1)
        ep_name = input(f"Episode Title [{clean_ep_title}]: ").strip() or clean_ep_title

        print(f"\nDownloading '{raw_fn}' directly into Jellyfin hierarchy...")
        success, saved_rel = scraper.download_tv_episode(
            show_title=selected["title"],
            year=selected.get("year"),
            season_num=season_num,
            ep_num=ep_num,
            ep_title=ep_name,
            media_url=chosen_file["url"]
        )

        if success:
            print(f"\nSuccessfully downloaded to Jellyfin format: {saved_rel}")
            play_ans = prompt_choice("Play downloaded video now? (y/n) [y]: ", ["y", "n", ""])
            if play_ans.lower() in ("y", ""):
                for root in get_tv_directories(scraper):
                    cand = os.path.join(root, saved_rel)
                    if os.path.exists(cand):
                        play_video_file(cand)
                        break
        else:
            print("Download failed.")

def _inspect_tv_show_dialog(scraper: MediaScraper, show_id: int):
    print("\nFetching complete episode guide and seasons from TVMaze...")
    details = scraper.get_tv_show_details(show_id)
    if "error" in details and not details.get("title"):
        print(f"Error fetching TV show details: {details.get('error')}")
        return

    title = details.get("title", "Unknown")
    year = details.get("year")
    genres = details.get("genres", [])
    status = details.get("status", "Unknown")
    summary = details.get("summary", "")
    seasons = details.get("seasons", [])
    episodes = details.get("episodes", [])
    total_episodes = len(episodes)

    series_folder = get_tv_series_folder(scraper, title, year=year)

    while True:
        existing_vids = []
        if os.path.isdir(series_folder):
            for root, _, files in os.walk(series_folder):
                for f in files:
                    if f.endswith(".part"):
                        continue
                    if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                        fp = os.path.join(root, f)
                        try:
                            if os.path.getsize(fp) > 1024 * 512:
                                existing_vids.append(fp)
                        except OSError:
                            pass

        print("\n" + "=" * 75)
        print(f"  Title:    {title} ({year or 'N/A'})")
        print(f"  Status:   {status}")
        print(f"  Genres:   {', '.join(genres) if genres else 'N/A'}")
        print(f"  Seasons:  {len(seasons)} season(s) | Total Episodes: {total_episodes}")
        if existing_vids:
            print(f"  Downloaded in Jellyfin Format: {len(existing_vids)} episode(s)")
        print(f"  Location: {os.path.abspath(series_folder)}")

        if summary:
            print("\n  Overview:")
            print("  " + "-" * 71)
            for line in textwrap.wrap(summary, width=71):
                print(f"  {line}")
            print("  " + "-" * 71)
        print("=" * 75)

        print("\nOptions:")
        print("  [1] Browse Seasons & Episode List")
        print("  [2] Search & Download Episodes for this Show (Internet Archive Library)")
        print("  [3] Download Episode by Direct Video Stream URL (Auto-Jellyfin Format)")
        valid_opts = ["1", "2", "3", "0"]
        if existing_vids:
            print("  [4] Watch / Play Downloaded Episode in Video Player")
            valid_opts.append("4")
        print("  [0] Return to Search Results")

        opt = prompt_choice(f"Choice [{', '.join(valid_opts)}]: ", valid_opts)
        if opt == "0":
            return
        elif opt == "1":
            _browse_tv_episodes(title, year, episodes)
        elif opt == "2":
            _archive_tv_search_dialog(scraper, default_query=title)
        elif opt == "3":
            _download_tv_url_dialog(scraper, title, year, episodes)
        elif opt == "4" and existing_vids:
            _play_episode_from_folder(series_folder)

def interactive_tv_shows_studio(scraper: MediaScraper):
    while True:
        print("\n--- [ TV Shows Studio (Jellyfin Format) ] ---")
        print("  [1] Search TV Show by Title (TVMaze Global Episode Guide)")
        print("  [2] Search & Download TV Shows (Internet Archive: 100,000+ Series & Episodes)")
        print("  [3] Download TV Show Episode by Stream URL (Auto-Jellyfin Format)")
        print("  [4] Watch / Play Downloaded TV Show Episode (Desktop Video Player)")
        print("  [0] Back to Main Menu")
        opt = prompt_choice("Choice [1, 2, 3, 4, 0]: ", ["1", "2", "3", "4", "0"])

        if opt == "0":
            return
        elif opt == "1":
            query = input("\nEnter TV show title or keyword: ").strip()
            if not query:
                continue

            print(f"\nSearching TVMaze for '{query}'...")
            results = scraper.search_tv_shows(query, limit=15)
            if not results:
                print(f"No TV shows found matching '{query}'.")
                continue

            while True:
                print(f"\nFound {len(results)} TV Shows on TVMaze for '{query}':")
                print("-" * 75)
                for idx, r in enumerate(results, 1):
                    yr = f" ({r['year']})" if r.get('year') else ""
                    net = f" [{r['network']}]" if r.get('network') else ""
                    rat = f" [Rating: {r['rating']}]" if r.get('rating') and r['rating'] != 'N/A' else ""
                    print(f"  [{idx:2d}] {r['title']}{yr}{net}{rat}")
                print("-" * 75)

                choice = prompt_int(f"Choose TV show to inspect / manage [1-{len(results)}] or [0] to return", min_val=0, max_val=len(results))
                if choice == 0:
                    break

                selected = results[choice - 1]
                _inspect_tv_show_dialog(scraper, selected["id"])
        elif opt == "2":
            _archive_tv_search_dialog(scraper)
        elif opt == "3":
            title = input("\nEnter TV show name: ").strip()
            if not title:
                continue
            year_input = input("Enter release year (optional, e.g. 2020): ").strip()
            year = year_input if year_input else None
            _download_tv_url_dialog(scraper, title, year, episodes=[])
        elif opt == "4":
            interactive_play_tv(scraper)


def prompt_and_download_movie(scraper: MediaScraper, target: Any):
    provider = "archive_movie"
    title = ""
    year = None
    identifier = None

    if isinstance(target, dict):
        provider = target.get("provider", "archive_movie")
        identifier = target.get("identifier") or target.get("id") or target.get("slug")
        title = target.get("title", "")
        year = target.get("year")
    else:
        identifier = str(target).strip()
        title = identifier

    print(f"\n--- [ Movie Download Configuration: {title or identifier} ] ---")
    print("Select Preferred Resolution:")
    print("  [1] Best Available / 1080p Full HD [Default]")
    print("  [2] 720p HD")
    print("  [3] 480p Standard Definition")
    q_opt = prompt_choice("Choose resolution [1, 2, 3] [1]: ", ["1", "2", "3", ""])
    q_map = {"1": "best", "2": "720p", "3": "480p", "": "best"}
    quality = q_map.get(q_opt, "best")

    voice_pref = "dub"
    strict_voice = False
    if provider in ("hianime", "tokyoinsider"):
        print("\nAudio / Voice Preference (Anime Movies):")
        print("  [1] English Dub (English Voice Acting) [Default]")
        print("  [2] English Sub (Original Japanese Audio with Subtitles)")
        v_opt = prompt_choice("Choose voice preference [1, 2] [1]: ", ["1", "2", ""])
        voice_pref = "dub" if v_opt in ("1", "") else "sub"

    print(f"\nStarting download for movie: '{title or identifier}' [{quality.upper()}]...")
    stats = scraper.download_movie(
        target,
        quality=quality,
        voice_pref=voice_pref,
        strict_voice=strict_voice
    )

    if stats.get("success"):
        play_now = prompt_choice("\nPlay this movie now in Desktop Video Player? (y/n) [y]: ", ["y", "n", ""])
        if play_now in ("y", ""):
            _play_episode_from_folder(stats["folder"])

def _browse_archive_movies_dialog(scraper: MediaScraper):
    collections = [
        ("feature_films", "Feature Films & World Cinema"),
        ("SciFi_Horror", "Sci-Fi & Horror Cinema Classics"),
        ("Film_Noir", "Film Noir & Crime Thrillers"),
        ("Comedy_Films", "Classic Comedy Feature Films"),
        ("silent_films", "Silent Era Masterpieces & Classics")
    ]
    print("\n--- [ Browse Feature Films & Cinema (Internet Archive) ] ---")
    for idx, (col_id, col_name) in enumerate(collections, 1):
        print(f"  [{idx}] {col_name}")
    print("  [0] Back to Studio")
    c_choice = prompt_int(f"Choose cinema category [1-{len(collections)}] or [0] to return", min_val=0, max_val=len(collections))
    if c_choice == 0:
        return

    chosen_col, chosen_name = collections[c_choice - 1]
    print(f"\nFetching top movies from '{chosen_name}'...")
    movies = scraper.browse_movies(collection=chosen_col, limit=25)
    if not movies:
        print("No movies found in this collection.")
        return

    while True:
        print(f"\n{chosen_name} (Top {len(movies)} Films):")
        print("-" * 75)
        for idx, m in enumerate(movies, 1):
            yr = f" ({m['year']})" if m.get('year') else ""
            dls = f" [Downloads: {m['downloads']:,}]" if m.get('downloads') else ""
            print(f"  [{idx:2d}] {m['title']}{yr}{dls}")
        print("-" * 75)

        choice = prompt_int(f"Choose movie to inspect / download [1-{len(movies)}] or [0] to return", min_val=0, max_val=len(movies))
        if choice == 0:
            break

        selected = movies[choice - 1]
        print(f"\n--- [ {selected['title']} ({selected.get('year') or 'N/A'}) ] ---")
        if selected.get('summary'):
            print(f"Synopsis: {selected['summary']}")
        print(f"Archive Details: {selected.get('url', '')}")

        files = scraper.get_archive_movie_files(selected['identifier'])
        if files:
            print(f"\nAvailable Video Streams ({len(files)} files):")
            for f_i, f in enumerate(files[:5], 1):
                print(f"  [{f_i}] {f['resolution']:<18} ({f['size_str']}) - {f['name']}")

        act = prompt_choice("\nDownload this film to your Jellyfin library? (y/n) [y]: ", ["y", "n", ""])
        if act in ("y", ""):
            prompt_and_download_movie(scraper, selected)

def interactive_movies_studio(scraper: MediaScraper):
    while True:
        print("\n--- [ Movie & Cinema Studio (Anime Movies & Feature Films) ] ---")
        print("  [1] Search Movies (HiAnime Anime Films & Archive.org Cinema)")
        print("  [2] Browse Classic Feature Films & Collections (Internet Archive)")
        print("  [3] Download Movie by URL or Slug (HiAnime, Archive.org or Direct MP4)")
        print("  [4] Watch / Play Downloaded Movie (Desktop Video Player with Resume Tracking)")
        print("  [0] Back to Main Menu")
        opt = prompt_choice("Choice [1, 2, 3, 4, 0]: ", ["1", "2", "3", "4", "0"])

        if opt == "0":
            return
        elif opt == "1":
            query = input("\nEnter movie title or keyword: ").strip()
            if not query:
                continue
            print(f"\nSearching for movie '{query}'...")
            results = scraper.search_movies(query, limit=25)
            if not results:
                print(f"No movies found matching '{query}'.")
                continue

            while True:
                print(f"\nFound {len(results)} Movie(s) for '{query}':")
                print("-" * 75)
                for idx, r in enumerate(results, 1):
                    p_badge = "[HiAnime]" if r.get("provider") == "hianime" else ("[TI]" if r.get("provider") == "tokyoinsider" else "[Archive]")
                    yr = f" ({r['year']})" if r.get('year') else ""
                    tag = f" [{r.get('voice_tag')}]" if r.get('voice_tag') else ""
                    print(f"  [{idx:2d}] {p_badge:<11} {r['title']}{yr}{tag}")
                print("-" * 75)

                choice = prompt_int(f"Choose movie to inspect / download [1-{len(results)}] or [0] to return", min_val=0, max_val=len(results))
                if choice == 0:
                    break

                selected = results[choice - 1]
                prompt_and_download_movie(scraper, selected)
        elif opt == "2":
            _browse_archive_movies_dialog(scraper)
        elif opt == "3":
            url_or_slug = input("\nEnter Movie URL or Identifier (HiAnime, Archive.org, or Direct MP4): ").strip()
            if url_or_slug:
                prompt_and_download_movie(scraper, url_or_slug)
        elif opt == "4":
            interactive_play_movie(scraper)

def interactive_play_movie(scraper: MediaScraper):
    roots = get_movie_directories(scraper)
    valid_movies = []
    seen_paths = set()
    for m_root in roots:
        if not os.path.isdir(m_root):
            continue
        movie_dirs = [d for d in os.listdir(m_root) if os.path.isdir(os.path.join(m_root, d))]
        for d in movie_dirs:
            p = os.path.join(m_root, d)
            if p in seen_paths:
                continue
            seen_paths.add(p)
            vids = []
            for r_dir, _, files in os.walk(p):
                for f in files:
                    if f.endswith(".part"):
                        continue
                    if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')):
                        fp = os.path.join(r_dir, f)
                        try:
                            if os.path.getsize(fp) > 1024 * 512:
                                vids.append(fp)
                        except OSError:
                            pass
            if vids:
                last_p = progress.get_watch_progress(p)
                watched_eps = progress.get_watched_episodes(p)
                dur = get_video_duration(vids[0]) if vids else None
                dur_str = progress.format_seconds(dur) if dur else ""
                sz_mb = os.path.getsize(vids[0]) / (1024 * 1024) if vids else 0
                sz_str = f"{sz_mb / 1024:.2f} GB" if sz_mb >= 1024 else f"{sz_mb:.0f} MB"
                valid_movies.append({
                    "title": d,
                    "path": p,
                    "file": vids[0],
                    "duration_str": dur_str,
                    "size_str": sz_str,
                    "progress": last_p,
                    "watched": len(watched_eps) > 0,
                    "last_updated": (last_p.get("timestamp") or "") if last_p else ""
                })

    if not valid_movies:
        primary_root = roots[0] if roots else "movies"
        print(f"\nNo downloaded movies found in '{primary_root}'.")
        print("Search or download a movie first using Option [6] Movie Studio!")
        return

    # Sort valid movies so most recently watched or added is first
    valid_movies.sort(key=lambda s: s.get("last_updated") or "", reverse=True)

    print("\nSelect Movie to Watch [Jellyfin Standard]:")
    print("-" * 75)
    for idx, m in enumerate(valid_movies, 1):
        prog_str = ""
        w = m["progress"]
        if w:
            pos = w.get("position_sec")
            dur = w.get("duration_sec")
            pct = w.get("percent", 0.0)
            if w.get("status") == "completed" or pct >= 95.0:
                prog_str = " [Status: Watched (100%)]"
            elif pos and dur:
                pos_s = progress.format_seconds(pos)
                dur_s = progress.format_seconds(dur)
                prog_str = f" [Resume: {pos_s} / {dur_s} ({pct:.1f}%)]"
        info_parts = [m["size_str"]]
        if m["duration_str"]:
            info_parts.append(m["duration_str"])
        info_text = f" ({' | '.join(info_parts)})" if info_parts else ""
        print(f"  [{idx:2d}] {m['title']}{info_text}{prog_str}")
    print("-" * 75)

    choice = prompt_int(f"Choose movie to play [1-{len(valid_movies)}] or [0] to return", min_val=0, max_val=len(valid_movies))
    if choice > 0:
        _play_episode_from_folder(valid_movies[choice - 1]["path"])

def list_downloaded(scraper: MediaScraper):
    import progress
    out_dir = scraper.output_dir
    print(f"\n--- [ Library & Watch Progress in '{out_dir}' ] ---")
    if not os.path.exists(out_dir):
        print("No downloaded folders found.")
        return

    items = []
    seen_paths = set()

    # 1. Anime series folders
    for a_root in get_anime_directories(scraper):
        if not os.path.isdir(a_root):
            continue
        for d in sorted(os.listdir(a_root)):
            s_path = os.path.join(a_root, d)
            s_norm = os.path.normcase(os.path.abspath(s_path))
            if not os.path.isdir(s_path) or s_norm in seen_paths:
                continue
            vids = []
            for r_dir, _, files in os.walk(s_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')) and not f.endswith(".part"):
                        vids.append(f)
            if vids:
                seen_paths.add(s_norm)
                items.append({
                    "name": d,
                    "title": d,
                    "path": s_path,
                    "type": "anime",
                    "label": "[Anime]   ",
                    "info": f"{len(vids)} episodes [Jellyfin]"
                })

    # 2. TV series folders
    for t_root in get_tv_directories(scraper):
        if not os.path.isdir(t_root):
            continue
        for d in sorted(os.listdir(t_root)):
            s_path = os.path.join(t_root, d)
            s_norm = os.path.normcase(os.path.abspath(s_path))
            if not os.path.isdir(s_path) or s_norm in seen_paths:
                continue
            vids = []
            for r_dir, _, files in os.walk(s_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')) and not f.endswith(".part"):
                        vids.append(f)
            if vids:
                seen_paths.add(s_norm)
                items.append({
                    "name": d,
                    "title": d,
                    "path": s_path,
                    "type": "tv",
                    "label": "[TV Show] ",
                    "info": f"{len(vids)} episodes [Jellyfin]"
                })

    # 3. Movie folders
    for m_root in get_movie_directories(scraper):
        if not os.path.isdir(m_root):
            continue
        for d in sorted(os.listdir(m_root)):
            s_path = os.path.join(m_root, d)
            s_norm = os.path.normcase(os.path.abspath(s_path))
            if not os.path.isdir(s_path) or s_norm in seen_paths:
                continue
            vids = []
            for r_dir, _, files in os.walk(s_path):
                for f in files:
                    if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')) and not f.endswith(".part"):
                        vids.append(os.path.join(r_dir, f))
            if vids:
                seen_paths.add(s_norm)
                sz_mb = os.path.getsize(vids[0]) / (1024 * 1024)
                sz_str = f"{sz_mb / 1024:.2f} GB" if sz_mb >= 1024 else f"{sz_mb:.0f} MB"
                items.append({
                    "name": d,
                    "title": d,
                    "path": s_path,
                    "type": "movie",
                    "label": "[Movie]   ",
                    "info": f"Feature Film ({sz_str}) [Jellyfin]"
                })

    if not items:
        print(f"No media series or movies downloaded yet in '{out_dir}'.")
        print("\nQuick Actions: [O]pen Folder in File Explorer | [S]et Download Folder | [0] Back")
        act = input("Choice: ").strip().lower()
        if act == "o":
            import config
            config.open_in_file_manager(out_dir)
        elif act == "s":
            interactive_configure_download_dir(scraper)
        return

    print("-" * 75)
    for idx, item in enumerate(items, 1):
        s_path = item["path"]
        print(f"  [{idx:2d}] {item['label']} {item['title']} ({item['info']})")

        prog_parts = []
        if item["type"] in ("anime", "tv"):
            w_prog = progress.get_watch_progress(s_path)
            watched_eps = progress.get_watched_episodes(s_path)
            m_cnt = re.search(r'(\d+)', item['info'])
            tot_vids = int(m_cnt.group(1)) if m_cnt else 1
            w_cnt = len(watched_eps)
            pct = round((w_cnt / max(1, tot_vids)) * 100.0, 1)
            if w_prog:
                last_ep = w_prog.get("episode_title") or w_prog.get("rel_path") or ""
                if len(last_ep) > 28:
                    last_ep = "..." + last_ep[-25:]
                prog_parts.append(f"Watch: {w_cnt}/{tot_vids} eps ({pct}%) | Last: {last_ep}")
            elif w_cnt > 0:
                prog_parts.append(f"Watch: {w_cnt}/{tot_vids} eps ({pct}%)")
        elif item["type"] == "movie":
            w_prog = progress.get_watch_progress(s_path)
            if w_prog:
                pos = w_prog.get("position_sec")
                dur = w_prog.get("duration_sec")
                pct = w_prog.get("percent", 0.0)
                if w_prog.get("status") == "completed" or pct >= 95.0:
                    prog_parts.append("Status: Fully Watched (100%)")
                elif pos and dur:
                    pos_s = progress.format_seconds(pos)
                    dur_s = progress.format_seconds(dur)
                    prog_parts.append(f"Resume: {pos_s} / {dur_s} ({pct:.1f}%)")
                else:
                    prog_parts.append(f"Progress: {pct:.1f}%")

        if prog_parts:
            print(f"      Status: {' | '.join(prog_parts)}")

    print("-" * 75)
    print("Quick Actions: [1-N] Select Media to Play | [W]atch Last Played | [O]pen in Explorer | [S]et Folder | [0] Back")
    act = input("Choice: ").strip().lower()
    if act.isdigit() and 1 <= int(act) <= len(items):
        selected = items[int(act) - 1]
        _play_episode_from_folder(selected["path"])
    elif act == "w":
        if len(items) == 1:
            _play_episode_from_folder(items[0]["path"])
        else:
            print("\nSelect Media to Watch:")
            for v_i, vit in enumerate(items, 1):
                print(f"  [{v_i}] {vit['label']} {vit['title']}")
            v_choice = prompt_int(f"Choose media [1-{len(items)}] or [0] to cancel", min_val=0, max_val=len(items))
            if v_choice > 0:
                _play_episode_from_folder(items[v_choice - 1]["path"])
    elif act == "o":
        import config
        config.open_in_file_manager(scraper.output_dir)
    elif act == "s":
        interactive_configure_download_dir(scraper)


def interactive_configure_download_dir(scraper: MediaScraper):
    """Interactive dialog to configure and persist the media download and Jellyfin directory."""
    import config
    print("\n========================================================================")
    print("  Configure Download & Jellyfin Media Directory")
    print("========================================================================")
    curr_dir = scraper.output_dir
    paths = config.resolve_jellyfin_paths(curr_dir)
    print(f"Current Download Directory:\n  Root:   {curr_dir}")
    print(f"  Anime:  {paths.get('anime')}")
    print(f"  TV:     {paths.get('tv')}")
    print(f"  Movies: {paths.get('movie')}")
    if paths.get("is_dedicated_library"):
        print(f"  Dedicated Mode: Direct {paths.get('dedicated_type').upper()} library targeted")
    print("------------------------------------------------------------------------")
    print("Enter a new directory path (e.g. D:\\Jellyfin or C:\\Media\\Movies),")
    print("[D] to reset to default (Book_Files),")
    print("[O] to open current folder in File Explorer,")
    print("or press [Enter] to keep current setting.")
    val = input("\nPath / Choice: ").strip()
    if not val:
        print("Directory unchanged.")
        return
    if val.lower() == "o":
        print(f"\nOpening directory in file explorer: {curr_dir}")
        config.open_in_file_manager(curr_dir)
        return
    if val.lower() in ("d", "default"):
        val = os.path.join(config.PROJECT_DIR, "Book_Files")

    ok, msg, new_paths = config.set_download_dir(val)
    if ok:
        scraper.output_dir = new_paths["root"]
        print(f"\n[OK] {msg}")
        print(f"  Anime Library:    {new_paths.get('anime')}")
        print(f"  TV Shows Library: {new_paths.get('tv')}")
        print(f"  Movies Library:   {new_paths.get('movie')}")
        if new_paths.get("is_dedicated_library"):
            print(f"  Dedicated Mode:   {new_paths.get('dedicated_type').upper()} library targeted directly")
        print("All future downloads and library scans will use this directory.")
    else:
        print(f"\n[ERROR] {msg}")


def main_menu():
    print_banner()
    scraper = MediaScraper()

    while True:
        import progress

        # Show last active media progress if available
        last_active = progress.get_last_active_series(scraper.output_dir)
        if last_active:
            s_name = last_active.get("series", "")
            w_info = last_active.get("watch") or last_active.get("anime") or last_active.get("tv")
            m_type = last_active.get("media_type") or "video"
            if w_info:
                watched_eps = w_info.get("watched_episodes", [])
                tot = w_info.get("total_episodes") or 1
                watched_cnt = len(watched_eps) if watched_eps else (w_info.get("watched_count") or (1 if w_info.get("episode_file") else 0))
                pct = round((watched_cnt / max(1, tot)) * 100.0, 1)
                last_ep = w_info.get("episode_title") or w_info.get("rel_path") or ""
                if len(last_ep) > 36:
                    last_ep = "..." + last_ep[-33:]
                type_tag = "[Movie]" if m_type == "movie" else "[Show]"
                if m_type == "movie":
                    pos_sec = w_info.get("current_position_sec") or w_info.get("position_sec")
                    dur_sec = w_info.get("current_duration_sec") or w_info.get("duration_sec")
                    if pos_sec and dur_sec:
                        pos_str = progress.format_seconds(pos_sec)
                        dur_str = progress.format_seconds(dur_sec)
                        print(f"\n[In Progress: {type_tag} {s_name} | Resume at {pos_str} / {dur_str} ({pct}%)]")
                    else:
                        print(f"\n[In Progress: {type_tag} {s_name} | Status: {pct}% watched]")
                else:
                    print(f"\n[In Progress: {type_tag} {s_name} | Watched: {watched_cnt}/{tot} eps ({pct}%) | Last: {last_ep}]")
                print("Quick Resume: Press [W] to Watch")

        print("\nMain Menu:")
        print("  -- Anime Studio --")
        print("  [1] Search Anime          - HiAnime English Dubs & TokyoInsider Fan-Subs")
        print("  [2] Browse Anime          - Popular, New Releases, and A-Z Index")
        print("  [3] Play Anime Episode    - Video Player with Resume & Timestamp Tracking")
        print("\n  -- Television Studio --")
        print("  [4] TV Shows Studio       - TVMaze Series Guide & Jellyfin Downloader")
        print("  [5] Play TV Show Episode  - Video Player with Resume & Timestamp Tracking")
        print("\n  -- Movies & Cinema Studio --")
        print("  [6] Movie Studio          - Anime Movies, Classic Cinema & Feature Films")
        print("  [7] Play Movie            - Desktop Video Player with Resume Tracking")
        print("\n  -- Library & Progress --")
        print("  [8] Library & Progress    - Downloaded Anime, TV Shows & Movies Watch History")
        print("\n  -- Settings & System --")
        print("  [9] Open Download Folder  - Open Jellyfin / Media directory in File Explorer")
        print("  [10] Configure Folder     - Set download & Jellyfin directory path")
        print("  [0] Exit")

        choice = input("\nEnter choice [0-10, W, S]: ").strip().lower()
        if choice == "w":
            if last_active and (last_active.get("watch") or last_active.get("path")):
                s_path = last_active.get("path")
                if not s_path or not os.path.isdir(s_path):
                    s_name = last_active.get("series", "")
                    s_path = get_anime_series_folder(scraper, s_name)
                    if not os.path.isdir(s_path):
                        s_path = get_tv_series_folder(scraper, s_name)
                    if not os.path.isdir(s_path):
                        s_path = get_movie_folder(scraper, s_name)
                if s_path and os.path.isdir(s_path):
                    _play_episode_from_folder(s_path)
                else:
                    interactive_play_anime(scraper)
            else:
                interactive_play_anime(scraper)
        elif choice == "1":
            interactive_anime_studio(scraper)
        elif choice == "2":
            interactive_browse_anime(scraper)
        elif choice == "3":
            interactive_play_anime(scraper)
        elif choice == "4":
            interactive_tv_shows_studio(scraper)
        elif choice == "5":
            interactive_play_tv(scraper)
        elif choice == "6":
            interactive_movies_studio(scraper)
        elif choice == "7":
            interactive_play_movie(scraper)
        elif choice == "8":
            list_downloaded(scraper)
        elif choice == "9":
            import config
            print(f"\nOpening download directory in file explorer:\n  Path: {scraper.output_dir}")
            ok, msg = config.open_in_file_manager(scraper.output_dir)
            if not ok:
                print(f"Failed to open directory: {msg}")
        elif choice in ("10", "s"):
            interactive_configure_download_dir(scraper)
        elif choice == "0":
            print("\nExiting Alexandria. Goodbye!\n")
            try:
                scraper.close()
            except Exception:
                pass
            sys.exit(0)
        else:
            print("Invalid choice, please enter 0-10, W, or S.")

def parse_cli_args():
    parser = argparse.ArgumentParser(
        description="Alexandria - High-Performance Anime, TV & Movie Streaming Media Studio"
    )
    parser.add_argument(
        "--anime",
        type=str,
        metavar="QUERY_OR_URL",
        help="Search or download anime series from HiAnime or TokyoInsider (e.g. 'naruto' or full URL)"
    )
    parser.add_argument(
        "--browse-anime",
        nargs="?",
        const="popular",
        metavar="SECTION_OR_LETTER",
        help="Browse anime series (e.g. --browse-anime popular, new, or letter like N)"
    )
    parser.add_argument(
        "--tv",
        type=str,
        metavar="QUERY_OR_SHOW",
        help="Search TV shows via TVMaze (e.g. 'breaking bad' or 'stranger things')"
    )
    parser.add_argument(
        "--play-tv",
        type=str,
        nargs="?",
        const="",
        metavar="SERIES",
        help="Play a downloaded TV show episode in desktop video player with resume tracking"
    )
    parser.add_argument(
        "--movie",
        type=str,
        metavar="QUERY_OR_URL",
        help="Search or download movie from HiAnime, TokyoInsider, or Archive.org (e.g. 'spirited away' or 'night of the living dead')"
    )
    parser.add_argument(
        "--browse-movies",
        nargs="?",
        const="feature_films",
        metavar="COLLECTION",
        help="Browse classic feature films and cinema (e.g. feature_films, scifihorror, film_noir, classic_movies)"
    )
    parser.add_argument(
        "--play-movie",
        type=str,
        nargs="?",
        const="",
        metavar="TITLE",
        help="Play a downloaded movie in desktop video player with resume tracking"
    )
    parser.add_argument(
        "--quality",
        type=str,
        default="best",
        help="Preferred video download quality ('best', '1080p', '720p', '480p')"
    )
    parser.add_argument(
        "--play-anime",
        type=str,
        nargs="?",
        const="",
        metavar="SERIES",
        help="Play a downloaded anime episode in desktop video player with resume tracking"
    )
    parser.add_argument(
        "--progress",
        action="store_true",
        help="View saved video watch history and episode progress across your library"
    )
    parser.add_argument(
        "--output-dir", "-o",
        type=str,
        default=None,
        help="Folder to store anime, tv, and movie media (default: configured download folder)"
    )
    parser.add_argument(
        "--set-download-dir", "--set-folder",
        type=str,
        metavar="PATH",
        help="Set and persist the media download and Jellyfin directory"
    )
    parser.add_argument(
        "--open-folder", "--open-dir",
        action="store_true",
        help="Open the configured download / Jellyfin directory in the system file explorer"
    )
    parser.add_argument(
        "--config", "--show-config",
        action="store_true",
        help="Display the current download directory and resolved Jellyfin library paths"
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.3,
        help="Delay in seconds between requests (default: 0.3)"
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Overwrite existing video files instead of skipping"
    )

    return parser.parse_args()

if __name__ == "__main__":
    from run import main
    main()
