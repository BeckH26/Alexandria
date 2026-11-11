# Changelog

All notable changes to the Alexandria project are documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

---

## [1.0.0] - 2026-11-11

### Initial Major Release

Alexandria 1.0.0 is the foundational release of the high-performance, terminal-native media workstation for Anime, Television series, and Feature Films.

#### Added
- **Movie & Cinema Studio (`--movie`, `--browse-movies`, `--play-movie`)**:
  - Full-featured integration across HiAnime (anime movies, 1080p HLS streams, dual audio), TokyoInsider (catalog anime films), and Internet Archive Cinema (vintage feature films, classic Hollywood, Film Noir, Sci-Fi/Horror, Silent Era).
  - High-speed direct MP4 downloading with streaming validation, ETA tracking, and transfer rate monitoring.
  - Automated post-download container repair via FFmpeg (`-movflags +faststart`) ensuring zero-latency seeking in desktop media players.
  - Pre-filtered curated collections: Feature Films, Sci-Fi & Horror, Film Noir, Comedy Films, and Silent Era.
  - Title relevance filtering algorithm (`is_title_relevant`) preventing fuzzy false positives and irrelevant trailer matches.

- **Anime Studio (`--anime`, `--browse-anime`, `--play-anime`)**:
  - Multi-provider support with prioritized HiAnime English Dubs and automated fallback to TokyoInsider.
  - Multi-resolution stream decoders: 1080p Full HD, 720p HD, and 480p SD.
  - Interactive catalog browser supporting alphabetical indexing (A-Z) and popularity categories.
  - Kitsu API title expansion and alias resolution.

- **Television Series Studio (`--tv`, `--play-tv`)**:
  - TVMaze integration for metadata, broadcast network schedules, and complete episode guides.
  - Internet Archive classic television episode scraper and downloader.

- **High-Speed HLS Sliding-Window Downloader**:
  - Deadlock-free sliding-window disk writer ensuring zero memory accumulation during large multi-gigabyte downloads.
  - Dynamic chunk concurrency limiting to prevent Cloudflare and CDN IP rate limits.
  - Automatic remuxing from transport stream (`.ts`) segments to valid ISOBMFF MP4.

- **Jellyfin Media Server Standard Compliance**:
  - Automatic organization into Jellyfin-compliant directory structures:
    - `Book_Files/anime/<Series> (<Year>)/Season <XX>/<Series> (<Year>) - S<XX>E<YY>.mp4`
    - `Book_Files/tv/<Series> (<Year>)/Season <XX>/<Series> (<Year>) - S<XX>E<YY>.mp4`
    - `Book_Files/movies/<Title> (<Year>)/<Title> (<Year>).mp4`

- **Desktop Playback & Watch Progress Tracker (`--progress`)**:
  - Native video player launch across Windows (`os.startfile`), macOS (`open`), and Linux (`xdg-open`).
  - Centralized watch progress database (`library_progress.json`) tracking watched episodes, movies, timestamps, runtime completion percentage, and last-watched positions.
  - Quick 1-click resume shortcut (`W`) in the main interactive menu to continue the next unwatched episode or in-progress film.

- **Persistent Download Directory & Jellyfin Library Integration (`--set-download-dir`, `--open-folder`, `--config`)**:
  - Direct configuration of custom download and Jellyfin media directories with persistent storage in `config.json`.
  - Native file manager launcher opening destination directory from CLI (`--open-folder`) or interactive menu (`[9]`).
  - Intelligent Jellyfin library structure resolution: automatically routes anime, tv, and movies into existing libraries (`Movies`, `TV Shows`, `Anime`) or dedicated single-library directories without redundant folder nesting.
  - Interactive configuration dialog in main menu (`[10]` or `[S]`) and media library viewer (`[S]`).

- **Packaging and Distribution**:
  - Standardized modern `pyproject.toml` and `setup.py` packaging.
  - CLI console script entry point `alexandria`.
  - Comprehensive automated smoke test suite.
  - GitHub Actions CI workflow for Python 3.10, 3.11, and 3.12.
