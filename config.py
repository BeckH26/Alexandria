"""
Alexandria Configuration and Jellyfin Library Integration Module.
Provides persistent download folder configuration, cross-platform file explorer launching,
and intelligent Jellyfin directory structure resolution.
"""

import os
import sys
import json
import subprocess
from typing import Dict, Any, Optional, Tuple

DEFAULT_FOLDER_NAME = "Book_Files"
PROJECT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_CONFIG_FILE = os.path.join(PROJECT_DIR, "config.json")
USER_CONFIG_DIR = os.path.expanduser("~/.alexandria")
USER_CONFIG_FILE = os.path.join(USER_CONFIG_DIR, "config.json")


def get_active_config_path() -> str:
    """Returns the config file path to use (project directory if writable, else user home)."""
    if os.path.exists(PROJECT_CONFIG_FILE):
        return PROJECT_CONFIG_FILE
    try:
        test_file = os.path.join(PROJECT_DIR, ".alexandria_perm_test")
        with open(test_file, "w") as f:
            f.write("test")
        os.remove(test_file)
        return PROJECT_CONFIG_FILE
    except Exception:
        os.makedirs(USER_CONFIG_DIR, exist_ok=True)
        return USER_CONFIG_FILE


def load_config() -> Dict[str, Any]:
    """Loads configuration from persistent JSON file or returns defaults."""
    # 1. Project config
    for candidate in [PROJECT_CONFIG_FILE, USER_CONFIG_FILE]:
        if os.path.isfile(candidate):
            try:
                with open(candidate, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, dict):
                        return data
            except Exception:
                pass
    return {}


def save_config(updates: Dict[str, Any]) -> Dict[str, Any]:
    """Updates and saves persistent configuration dictionary."""
    config_path = get_active_config_path()
    current = load_config()
    current.update(updates)
    try:
        os.makedirs(os.path.dirname(config_path), exist_ok=True)
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(current, f, indent=2)
    except Exception as e:
        print(f"Warning: Failed to save config to {config_path}: {e}")
    return current


def sanitize_input_path(path_str: str) -> str:
    """Normalizes and expands path string, removing surrounding quotes and expanding ~ and vars."""
    clean = path_str.strip().strip("'\"")
    clean = os.path.expandvars(clean)
    clean = os.path.expanduser(clean)
    return os.path.abspath(clean)


def get_download_dir() -> str:
    """
    Returns the configured media download directory.
    Priority:
      1. Persistent config.json 'download_dir'
      2. Existing Book_Files or book_files in project directory
      3. Default Book_Files in project directory
    """
    cfg = load_config()
    custom_dir = cfg.get("download_dir")
    if custom_dir and isinstance(custom_dir, str):
        sanitized = sanitize_input_path(custom_dir)
        return sanitized

    for candidate in ["Book_Files", "book_files"]:
        p = os.path.join(PROJECT_DIR, candidate)
        if os.path.isdir(p):
            return os.path.abspath(p)

    return os.path.abspath(os.path.join(PROJECT_DIR, DEFAULT_FOLDER_NAME))


def resolve_jellyfin_paths(base_dir: Optional[str] = None) -> Dict[str, Any]:
    """
    Intelligently analyzes a download directory for Jellyfin structure.
    Determines whether the path points to a root media folder or a specific dedicated library,
    and returns canonical paths for movies, tv, and anime.
    """
    root = sanitize_input_path(base_dir) if base_dir else get_download_dir()
    base_name = os.path.basename(os.path.normpath(root)).lower()

    # Case 1: Base directory itself is a dedicated library
    is_dedicated = False
    dedicated_type = None

    if base_name in ["movies", "movie", "films", "film", "cinema"]:
        is_dedicated = True
        dedicated_type = "movie"
        movie_path = root
    else:
        # Check if root has existing movie subfolder (respecting existing casing)
        movie_path = None
        if os.path.isdir(root):
            for candidate in ["Movies", "movies", "Films", "films"]:
                cp = os.path.join(root, candidate)
                if os.path.isdir(cp):
                    movie_path = cp
                    break
        if not movie_path:
            movie_path = os.path.join(root, "movies")

    if base_name in ["tv", "tv shows", "tvshows", "shows", "series", "television"]:
        is_dedicated = True
        dedicated_type = "tv"
        tv_path = root
    else:
        # Check if root has existing TV subfolder (respecting existing casing)
        tv_path = None
        if os.path.isdir(root):
            for candidate in ["TV Shows", "tv shows", "TV", "tv", "Shows", "shows", "Series", "series"]:
                cp = os.path.join(root, candidate)
                if os.path.isdir(cp):
                    tv_path = cp
                    break
        if not tv_path:
            tv_path = os.path.join(root, "tv")

    if base_name in ["anime", "animation"]:
        is_dedicated = True
        dedicated_type = "anime"
        anime_path = root
    else:
        # Check if root has existing anime subfolder
        anime_path = None
        if os.path.isdir(root):
            for candidate in ["Anime", "anime"]:
                cp = os.path.join(root, candidate)
                if os.path.isdir(cp):
                    anime_path = cp
                    break
        if not anime_path:
            anime_path = os.path.join(root, "anime")

    return {
        "root": root,
        "movie": movie_path,
        "tv": tv_path,
        "anime": anime_path,
        "is_dedicated_library": is_dedicated,
        "dedicated_type": dedicated_type
    }


def get_media_dir(media_type: str, base_dir: Optional[str] = None) -> str:
    """
    Returns the resolved directory for the specified media type ('movie', 'tv', 'anime'),
    automatically creating it if necessary.
    """
    paths = resolve_jellyfin_paths(base_dir)
    target = paths.get(media_type.lower()) or os.path.join(paths["root"], media_type.lower())
    try:
        os.makedirs(target, exist_ok=True)
    except Exception:
        pass
    return target


def set_download_dir(path_str: str) -> Tuple[bool, str, Dict[str, Any]]:
    """
    Sets and persists the media download and Jellyfin directory.
    Validates the path, verifies write permissions, and resolves subdirectories.
    """
    if not path_str or not path_str.strip():
        return False, "Provided path is empty.", {}

    target = sanitize_input_path(path_str)

    try:
        os.makedirs(target, exist_ok=True)
    except Exception as e:
        return False, f"Failed to create directory '{target}': {e}", {}

    # Verify write permissions
    test_file = os.path.join(target, ".alexandria_perm_test")
    try:
        with open(test_file, "w") as f:
            f.write("write_test")
        os.remove(test_file)
    except Exception as e:
        return False, f"Directory '{target}' is not writable: {e}", {}

    # Save to config
    save_config({
        "download_dir": target
    })

    resolved = resolve_jellyfin_paths(target)
    msg = f"Download directory configured successfully to: {target}"
    return True, msg, resolved


def open_in_file_manager(target_path: Optional[str] = None) -> Tuple[bool, str]:
    """
    Opens the target directory (or configured download directory) in the platform-native file explorer.
    Supports Windows (Explorer), macOS (Finder), and Linux (xdg-open).
    """
    path_to_open = sanitize_input_path(target_path) if target_path else get_download_dir()

    if not os.path.exists(path_to_open):
        try:
            os.makedirs(path_to_open, exist_ok=True)
        except Exception as e:
            return False, f"Directory does not exist and could not be created: {e}"

    norm_path = os.path.normpath(path_to_open)

    try:
        if sys.platform == "win32":
            # Windows shell open
            try:
                os.startfile(norm_path)
            except Exception:
                subprocess.Popen(["explorer.exe", norm_path])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", norm_path])
        else:
            subprocess.Popen(["xdg-open", norm_path])
        return True, f"Opened directory in file manager: {norm_path}"
    except Exception as e:
        return False, f"Failed to open file manager: {e}"
