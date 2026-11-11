"""
progress.py - Anime, TV & Movie Video Watching Progress Tracking for Alexandria.

Tracks and persists:
- Video watching progress for Anime, Television Shows, and Feature Films.
- Episode files, relative paths, season/episode numbers, and movie runtimes.
- Watched episode checklists, watched count, total episodes, percentage, and timestamps.
- Exact seek positions, durations, and completion statuses for instant quick-resume.
- Central library activity log to enable instant 1-click resume from the main menu.
- 100% text-based with zero emojis.
"""

import os
import re
import json
from datetime import datetime
from typing import Optional, Dict, Any, List

def format_time(ms: int) -> str:
    """Format milliseconds into MM:SS or HH:MM:SS."""
    if ms < 0:
        ms = 0
    total_seconds = int(ms // 1000)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def format_seconds(sec: float) -> str:
    """Format seconds into MM:SS or HH:MM:SS."""
    if sec < 0:
        sec = 0.0
    total_seconds = int(sec)
    hours = total_seconds // 3600
    minutes = (total_seconds % 3600) // 60
    seconds = total_seconds % 60
    if hours > 0:
        return f"{hours:02d}:{minutes:02d}:{seconds:02d}"
    return f"{minutes:02d}:{seconds:02d}"

def _get_progress_file(series_dir: str) -> str:
    return os.path.join(series_dir, "progress.json")

def _get_library_index_file(output_dir: str) -> str:
    return os.path.join(output_dir, "library_progress.json")

def load_series_progress(series_dir: str) -> Dict[str, Any]:
    """Load progress.json for a specific series directory, normalizing legacy keys."""
    p_file = _get_progress_file(series_dir)
    data: Dict[str, Any] = {}
    if os.path.exists(p_file):
        try:
            with open(p_file, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}

    if not isinstance(data, dict):
        data = {}

    series_name = data.get("series") or os.path.basename(os.path.normpath(series_dir))
    data["series"] = series_name

    # Normalize watching progress across watch, anime, and tv keys
    watch_data = data.get("watch") or data.get("anime") or data.get("tv")
    if isinstance(watch_data, dict):
        w_list = watch_data.get("watched_episodes")
        if not isinstance(w_list, list):
            w_list = []
        prev_f = watch_data.get("episode_file") or watch_data.get("rel_path")
        if prev_f:
            try:
                prev_rel = os.path.relpath(prev_f, series_dir).replace("/", "\\")
            except Exception:
                prev_rel = os.path.basename(prev_f)
            if prev_rel not in w_list and os.path.basename(prev_rel).lower() not in [os.path.basename(x).lower() for x in w_list]:
                w_list.append(prev_rel)
        watch_data["watched_episodes"] = w_list
        watch_data["watched_count"] = len(w_list)
        if "episodes" not in watch_data or not isinstance(watch_data["episodes"], dict):
            watch_data["episodes"] = {}
        # Backfill any watched items not yet in episodes dictionary
        for w in w_list:
            if w not in watch_data["episodes"]:
                watch_data["episodes"][w] = {
                    "status": "completed",
                    "percent": 100.0,
                    "position_sec": None,
                    "duration_sec": None,
                    "last_watched": watch_data.get("timestamp")
                }

    data["watch"] = watch_data
    data.setdefault("media_type", "video")
    data.setdefault("last_updated", None)
    return data

def _save_series_progress(series_dir: str, data: Dict[str, Any]):
    """Persist progress.json in the series directory and update parent/root library indexes."""
    os.makedirs(series_dir, exist_ok=True)
    p_file = _get_progress_file(series_dir)
    data["last_updated"] = datetime.now().isoformat()
    try:
        with open(p_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"[!] Warning: Could not save progress to {p_file}: {e}")

    # Update immediate parent directory index (e.g. media/anime or media)
    parent_dir = os.path.dirname(os.path.abspath(series_dir))
    _update_library_index(parent_dir, data)

    # If parent is a media subcategory, also update its grandparent (root media library)
    grandparent_dir = os.path.dirname(parent_dir)
    p_basename = os.path.basename(parent_dir).lower()
    if p_basename in ("anime", "tv", "movies", "shows", "films"):
        _update_library_index(grandparent_dir, data)

def _update_library_index(output_dir: str, series_data: Dict[str, Any]):
    """Update central library_progress.json for fast multi-series lookup."""
    index_file = _get_library_index_file(output_dir)
    index = {}
    if os.path.exists(index_file):
        try:
            with open(index_file, "r", encoding="utf-8") as f:
                index = json.load(f)
        except Exception:
            index = {}

    s_name = series_data.get("series", "Unknown")
    watch_data = series_data.get("watch") or series_data.get("anime") or series_data.get("tv")
    index[s_name] = {
        "series": s_name,
        "media_type": series_data.get("media_type") or "video",
        "watch": watch_data,
        "last_updated": series_data.get("last_updated")
    }

    try:
        with open(index_file, "w", encoding="utf-8") as f:
            json.dump(index, f, indent=2, ensure_ascii=False)
    except Exception:
        pass

def save_watch_progress(
    series_dir: str,
    episode_file: str,
    episode_title: str = "",
    season: Optional[int] = None,
    episode_num: Optional[int] = None,
    total_episodes: int = 1,
    episode_index: Optional[int] = None,
    media_type: str = "video",
    mark_completed: bool = True,
    position_sec: Optional[float] = None,
    duration_sec: Optional[float] = None,
    status: Optional[str] = None
):
    """
    Save user's video watching position in an anime, TV show, or video folder.
    Tracks episode file, relative path, season/episode numbers, per-episode
    timestamp/duration/percentage, watched episode list, and series progress.
    """
    prog = load_series_progress(series_dir)
    prog["media_type"] = media_type

    # Calculate relative path
    try:
        rel_path = os.path.relpath(episode_file, series_dir)
    except Exception:
        rel_path = os.path.basename(episode_file)

    fn = os.path.basename(episode_file)
    clean_ep_title = episode_title or fn

    # Parse season and episode numbers if not provided
    if season is None or episode_num is None:
        m_se = re.search(r's(\d+)e(\d+)', fn, re.I)
        if m_se:
            if season is None:
                season = int(m_se.group(1))
            if episode_num is None:
                episode_num = int(m_se.group(2))
        else:
            m_x = re.search(r'(\d+)x(\d+)', fn, re.I)
            if m_x:
                if season is None:
                    season = int(m_x.group(1))
                if episode_num is None:
                    episode_num = int(m_x.group(2))
            else:
                m_ep = re.search(r'(?:ep|episode)[_\s]*(\d+)', fn, re.I)
                if m_ep:
                    if season is None:
                        season = 1
                    if episode_num is None:
                        episode_num = int(m_ep.group(1))

    # Maintain watched episodes list and per-episode granular records
    existing_watch = prog.get("watch") or prog.get("anime") or prog.get("tv") or {}
    watched_list = existing_watch.get("watched_episodes", [])
    if not isinstance(watched_list, list):
        watched_list = []

    episodes_dict = existing_watch.get("episodes", {})
    if not isinstance(episodes_dict, dict):
        episodes_dict = {}

    norm_rel = rel_path.replace("/", "\\")
    target_fn = fn.lower()

    # Determine per-episode status, position, and completion percentage
    pos = max(0.0, position_sec) if position_sec is not None else None
    dur = max(0.0, duration_sec) if duration_sec is not None else None

    if dur and dur > 0 and pos is not None:
        calc_pct = min(100.0, round((pos / dur) * 100.0, 1))
    elif mark_completed:
        calc_pct = 100.0
    else:
        calc_pct = 0.0

    if status:
        ep_status = status.lower()
    elif mark_completed or calc_pct >= 90.0:
        ep_status = "completed"
        calc_pct = 100.0 if mark_completed else calc_pct
    elif pos is not None and pos > 15.0:
        ep_status = "in_progress"
    else:
        ep_status = "unwatched"

    episodes_dict[norm_rel] = {
        "status": ep_status,
        "position_sec": pos,
        "duration_sec": dur,
        "percent": calc_pct,
        "last_watched": datetime.now().isoformat()
    }

    if ep_status == "completed":
        already_watched = any(
            norm_rel.lower() == w.replace("/", "\\").lower() or target_fn == os.path.basename(w).lower()
            for w in watched_list
        )
        if not already_watched:
            watched_list.append(norm_rel)
    else:
        # If in progress or unwatched, remove from fully watched list
        watched_list = [
            w for w in watched_list
            if w.replace("/", "\\").lower() != norm_rel.lower() and os.path.basename(w).lower() != target_fn
        ]

    watched_count = len(watched_list)
    effective_total = max(total_episodes, watched_count, 1)
    series_pct = round((watched_count / effective_total) * 100.0, 1)

    watch_data = {
        "episode_file": episode_file,
        "rel_path": norm_rel,
        "episode_title": clean_ep_title,
        "season": season,
        "episode_num": episode_num,
        "episode_index": episode_index if episode_index is not None else episode_num,
        "total_episodes": effective_total,
        "watched_episodes": watched_list,
        "watched_count": watched_count,
        "series_percent": series_pct,
        "media_type": media_type,
        "episodes": episodes_dict,
        "current_position_sec": pos,
        "current_duration_sec": dur,
        "current_percent": calc_pct,
        "current_status": ep_status,
        "timestamp": datetime.now().isoformat()
    }

    prog["watch"] = watch_data
    prog["anime"] = watch_data
    prog["tv"] = watch_data

    _save_series_progress(series_dir, prog)

def get_watch_progress(series_dir: str) -> Optional[Dict[str, Any]]:
    """Retrieve video watching progress for an anime, TV show, or video folder."""
    prog = load_series_progress(series_dir)
    return prog.get("watch") or prog.get("anime") or prog.get("tv")

def get_all_episodes_detail(series_dir: str) -> Dict[str, Dict[str, Any]]:
    """Retrieve dictionary of granular per-episode progress records for a series."""
    w = get_watch_progress(series_dir)
    if not w:
        return {}
    eps = w.get("episodes")
    return eps if isinstance(eps, dict) else {}

def get_episode_detail(series_dir: str, rel_path: str) -> Optional[Dict[str, Any]]:
    """Retrieve granular progress details for a single episode."""
    all_eps = get_all_episodes_detail(series_dir)
    norm = rel_path.replace("/", "\\")
    if norm in all_eps:
        return all_eps[norm]
    # Fallback search by basename
    norm_fn = os.path.basename(norm).lower()
    for k, v in all_eps.items():
        if os.path.basename(k).lower() == norm_fn:
            return v
    return None

def get_watched_episodes(series_dir: str) -> List[str]:
    """Retrieve list of watched episode identifiers (relative paths) for a series."""
    w = get_watch_progress(series_dir)
    if not w:
        return []
    episodes = w.get("watched_episodes")
    if isinstance(episodes, list) and episodes:
        return episodes
    legacy_file = w.get("episode_file") or w.get("rel_path") or w.get("episode_title")
    if legacy_file:
        return [legacy_file]
    return []

def mark_episode_watched(
    series_dir: str,
    episode_rel_or_file: str,
    watched: bool = True,
    total_episodes: int = 1
):
    """Explicitly mark or unmark an episode as watched without launching playback."""
    prog = load_series_progress(series_dir)
    existing_watch = prog.get("watch") or prog.get("anime") or prog.get("tv") or {}
    watched_list = existing_watch.get("watched_episodes", [])
    if not isinstance(watched_list, list):
        watched_list = []

    episodes_dict = existing_watch.get("episodes", {})
    if not isinstance(episodes_dict, dict):
        episodes_dict = {}

    norm_target = episode_rel_or_file.replace("/", "\\")
    target_fn = os.path.basename(norm_target).lower()

    if watched:
        already_watched = any(
            norm_target.lower() == w.replace("/", "\\").lower() or target_fn == os.path.basename(w).lower()
            for w in watched_list
        )
        if not already_watched:
            watched_list.append(norm_target)
        episodes_dict[norm_target] = {
            "status": "completed",
            "percent": 100.0,
            "position_sec": None,
            "duration_sec": None,
            "last_watched": datetime.now().isoformat()
        }
    else:
        watched_list = [
            w for w in watched_list
            if w.replace("/", "\\").lower() != norm_target.lower() and os.path.basename(w).lower() != target_fn
        ]
        episodes_dict[norm_target] = {
            "status": "unwatched",
            "percent": 0.0,
            "position_sec": 0.0,
            "duration_sec": None,
            "last_watched": datetime.now().isoformat()
        }

    watched_count = len(watched_list)
    effective_total = max(total_episodes, watched_count, 1)
    series_pct = round((watched_count / effective_total) * 100.0, 1)

    if "watch" not in prog or not isinstance(prog["watch"], dict):
        prog["watch"] = {}

    prog["watch"]["watched_episodes"] = watched_list
    prog["watch"]["watched_count"] = watched_count
    prog["watch"]["total_episodes"] = effective_total
    prog["watch"]["series_percent"] = series_pct
    prog["watch"]["episodes"] = episodes_dict
    prog["watch"]["timestamp"] = datetime.now().isoformat()
    prog["anime"] = prog["watch"]
    prog["tv"] = prog["watch"]

    _save_series_progress(series_dir, prog)

def mark_all_episodes_watched(
    series_dir: str,
    video_files: List[str],
    watched: bool = True
):
    """Mark all episodes in a series as watched or clear all watch history."""
    prog = load_series_progress(series_dir)
    if "watch" not in prog or not isinstance(prog["watch"], dict):
        prog["watch"] = {}

    episodes_dict = {}
    if watched:
        watched_list = []
        for vf in video_files:
            try:
                rel = os.path.relpath(vf, series_dir).replace("/", "\\")
            except Exception:
                rel = os.path.basename(vf)
            watched_list.append(rel)
            episodes_dict[rel] = {
                "status": "completed",
                "percent": 100.0,
                "position_sec": None,
                "duration_sec": None,
                "last_watched": datetime.now().isoformat()
            }
        watched_count = len(watched_list)
        prog["watch"]["watched_episodes"] = watched_list
        prog["watch"]["watched_count"] = watched_count
        prog["watch"]["total_episodes"] = max(1, watched_count)
        prog["watch"]["series_percent"] = 100.0
    else:
        for vf in video_files:
            try:
                rel = os.path.relpath(vf, series_dir).replace("/", "\\")
            except Exception:
                rel = os.path.basename(vf)
            episodes_dict[rel] = {
                "status": "unwatched",
                "percent": 0.0,
                "position_sec": 0.0,
                "duration_sec": None,
                "last_watched": datetime.now().isoformat()
            }
        prog["watch"]["watched_episodes"] = []
        prog["watch"]["watched_count"] = 0
        prog["watch"]["total_episodes"] = max(1, len(video_files))
        prog["watch"]["series_percent"] = 0.0

    prog["watch"]["episodes"] = episodes_dict
    prog["watch"]["timestamp"] = datetime.now().isoformat()
    prog["anime"] = prog["watch"]
    prog["tv"] = prog["watch"]
    _save_series_progress(series_dir, prog)

def save_anime_progress(
    series_dir: str,
    episode_file: str,
    episode_title: str = ""
):
    """Backward-compatible helper: saves anime watching progress."""
    save_watch_progress(series_dir, episode_file, episode_title=episode_title, media_type="anime")

def get_anime_progress(series_dir: str) -> Optional[Dict[str, Any]]:
    """Backward-compatible helper: retrieves anime watching progress."""
    return get_watch_progress(series_dir)

def get_last_active_series(output_dir: Optional[str] = None) -> Optional[Dict[str, Any]]:
    """
    Find the series that the user most recently watched across the library.
    Scans root library and media subfolders (anime, tv, shows, movies).
    Returns dict with series name, media_type, watch, and path.
    """
    if output_dir is None:
        try:
            import config
            output_dir = config.get_download_dir()
        except Exception:
            output_dir = "media"

    candidates = []

    # 1. Check root library_progress.json
    root_index = _get_library_index_file(output_dir)
    if os.path.exists(root_index):
        try:
            with open(root_index, "r", encoding="utf-8") as f:
                data = json.load(f)
                for s_name, val in data.items():
                    if isinstance(val, dict) and val.get("last_updated"):
                        val["series"] = s_name
                        s_path = os.path.join(output_dir, s_name)
                        if not os.path.isdir(s_path):
                            for sub in ["anime", "tv", "movies", "shows", "Anime", "TV", "TV Shows", "Movies", "Films"]:
                                cand_sp = os.path.join(output_dir, sub, s_name)
                                if os.path.isdir(cand_sp):
                                    s_path = cand_sp
                                    break
                        if os.path.isdir(s_path):
                            val["path"] = s_path
                        candidates.append(val)
        except Exception:
            pass

    # 2. Check subcategory library_progress.json (anime, tv, movies, shows)
    for sub in ["anime", "tv", "movies", "shows", "Anime", "TV", "TV Shows", "Movies", "Films"]:
        sub_dir = os.path.join(output_dir, sub)
        sub_index = _get_library_index_file(sub_dir)
        if os.path.exists(sub_index):
            try:
                with open(sub_index, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    for s_name, val in data.items():
                        if isinstance(val, dict) and val.get("last_updated"):
                            val["series"] = s_name
                            s_path = os.path.join(sub_dir, s_name)
                            if os.path.isdir(s_path):
                                val["path"] = s_path
                            candidates.append(val)
            except Exception:
                pass

    # 3. Direct folder search for any progress.json not yet in index
    search_dirs = [output_dir]
    try:
        import config
        resolved = config.resolve_jellyfin_paths(output_dir)
        for key in ["anime", "tv", "movie"]:
            p = resolved.get(key)
            if p and os.path.isdir(p) and p not in search_dirs:
                search_dirs.append(p)
    except Exception:
        pass

    for sub in ["anime", "tv", "movies", "shows", "anime_files", "tv_files", "movie_files", "Anime", "TV", "TV Shows", "Movies", "Films"]:
        sd = os.path.join(output_dir, sub) if sub in ("anime", "tv", "movies", "shows", "Anime", "TV", "TV Shows", "Movies", "Films") else sub
        if os.path.isdir(sd) and sd not in search_dirs:
            search_dirs.append(sd)

    seen_paths = set()
    for sd in search_dirs:
        try:
            for d in os.listdir(sd):
                sp = os.path.join(sd, d)
                if os.path.isdir(sp) and sp not in seen_paths:
                    seen_paths.add(sp)
                    p_file = os.path.join(sp, "progress.json")
                    if os.path.exists(p_file):
                        try:
                            with open(p_file, "r", encoding="utf-8") as f:
                                p = json.load(f)
                                if p.get("last_updated"):
                                    p["path"] = sp
                                    p["series"] = p.get("series") or d
                                    candidates.append(p)
                        except Exception:
                            pass
        except Exception:
            pass

    if not candidates:
        return None

    # Deduplicate candidates by path or series name, keeping newest and most complete
    merged: Dict[str, Dict[str, Any]] = {}
    for c in candidates:
        key = c.get("path") or c.get("series")
        if not key:
            continue
        curr_ts = c.get("last_updated") or ""
        existing = merged.get(key)
        existing_ts = (existing.get("last_updated") or "") if existing else ""
        if existing is None or curr_ts >= existing_ts:
            # If path exists, enrich with full series progress if missing fields
            c_path = c.get("path")
            if c_path and os.path.isdir(c_path):
                p_full = load_series_progress(c_path)
                c["watch"] = p_full.get("watch") or c.get("watch") or p_full.get("anime") or p_full.get("tv")
                if not c.get("media_type"):
                    c["media_type"] = p_full.get("media_type")

                # If watch progress has incomplete total episodes, count actual video files on disk
                if c.get("watch") and (not c["watch"].get("total_episodes") or c["watch"].get("total_episodes") <= 1):
                    v_cnt = 0
                    for _, _, f_list in os.walk(c_path):
                        for vf in f_list:
                            if vf.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')) and not vf.endswith('.part'):
                                v_cnt += 1
                    if v_cnt > 1:
                        c["watch"]["total_episodes"] = v_cnt
                        w_cnt = c["watch"].get("watched_count") or len(c["watch"].get("watched_episodes", [])) or 1
                        c["watch"]["watched_count"] = w_cnt
                        c["watch"]["series_percent"] = round((w_cnt / v_cnt) * 100.0, 1)
            if not c.get("watch"):
                c["watch"] = c.get("anime") or c.get("tv")
            merged[key] = c

    sorted_candidates = sorted(merged.values(), key=lambda x: x.get("last_updated") or "", reverse=True)
    return sorted_candidates[0] if sorted_candidates else None
