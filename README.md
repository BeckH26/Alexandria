# Alexandria

```text
========================================================================
    _    _     _______  __    _    _   _ ____  ____  ___    _    
   / \  | |   | ____\ \/ /   / \  | \ | |  _ \|  _ \|_ _|  / \   
  / _ \ | |   |  _|  \  /   / _ \ |  \| | | | | |_) || |  / _ \  
 / ___ \| |___| |___ /  \  / ___ \| |\  | |_| |  _ < | | / ___ \ 
/_/   \_\_____|_____/_/\_\/_/   \_\_| \_|____/|_| \_\___/_/   \_\
            Universal Media Archive & Studio
========================================================================
```

[![Release](https://img.shields.io/badge/release-v1.0.0-blue.svg)](https://github.com/alexandria-media/alexandria/releases)
[![Python](https://img.shields.io/badge/python-3.10%20%7C%203.11%20%7C%203.12-brightgreen.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![CI](https://img.shields.io/badge/CI-passing-brightgreen.svg)](.github/workflows/ci.yml)
[![Jellyfin](https://img.shields.io/badge/Jellyfin-Compliant-purple.svg)](https://jellyfin.org/)

Alexandria is a terminal-based media workstation for finding, downloading, and watching anime, television series, and movies. It combines multiple streaming and catalog backends into a single clean CLI, downloads full seasons with fast multi-threaded HLS remuxing, organizes everything into Jellyfin-ready folders, and keeps track of your watch history so you can pick up right where you left off.

---

## What It Does

- **Anime Without the Headaches**: Search across HiAnime and TokyoInsider with support for 1080p, 720p, English dubs, and Japanese subs with intelligent fallback so downloads never fail on missing audio tracks.
- **Movies & Cinema**: Download full-length anime films, cult cinema, horror classics, film noir, and public domain feature films via Internet Archive and anime providers.
- **TV Shows & Episode Guides**: Search TV series via TVMaze, pull episode metadata, and download directly.
- **Ready for Jellyfin**: Alexandria names and sorts every file into the exact folder structure Jellyfin expects (`Show (Year)/Season 01/Show - S01E01.mp4`). If you point Alexandria at your Jellyfin library, it drops files directly into your existing setup without extra nesting.
- **Smooth Playback & Seeking**: Video chunks are remuxed into valid MP4 containers with `+faststart` metadata atoms, meaning files seek instantly in VLC, MPV, or Windows Media Player without playback stutters.
- **Built-in Watch Tracker**: Alexandria remembers what episode you watched last, what percentage you finished, and lets you hit `W` to immediately jump into the next unwatched episode in your favorite desktop player.

---

## Quick Start

### Option 1: Standalone Windows App (No Python Needed)

If you just want to run the program without installing Python or dealing with dependencies:

1. Grab `alexandria.exe` from the latest [GitHub Release](https://github.com/alexandria-media/alexandria/releases).
2. Put `alexandria.exe` in any folder you like (for example, `C:\Media` or on your storage drive).
3. Double-click `alexandria.exe` or open a terminal window in that folder and run:
   ```cmd
   alexandria.exe
   ```
4. That is it. All scrapers, providers, and settings work out of the box.

### Option 2: Run from Source with Python

Requirements: Python 3.10+ and FFmpeg (recommended for container repair; a built-in fallback is included).

```bash
# Clone the repo
git clone https://github.com/alexandria-media/alexandria.git
cd alexandria

# Install dependencies
pip install -r requirements.txt

# Launch the interactive studio
python run.py
```

You can also install it as a command on your PATH:
```bash
pip install -e .
alexandria
```

---

## How to Use It

### Interactive Dashboard

Running Alexandria without any arguments launches the full interactive menu where you can browse, search, configure folders, and resume watching with single keystrokes:

```bash
python run.py
# Or if using the exe:
alexandria.exe
```

Inside the menu:
- `[1]` Search Anime (HiAnime & TokyoInsider)
- `[2]` Browse Anime (Popular, Trending, or A-Z)
- `[3]` Search TV Shows (TVMaze)
- `[4]` Search Movies (Anime Films & Cinema)
- `[5]` Browse Classic Feature Films & Collections
- `[6]` Play Next Anime Episode (Watch History)
- `[7]` Play Next TV Episode
- `[8]` Play Next Movie
- `[9]` View Library & Episode Progress
- `[10]` Set Download Folder / Jellyfin Path
- `[O]` Open Current Media Folder in File Explorer
- `[W]` Instant Quick Resume (plays whatever you were watching last)

---

### Command Line Flags

If you prefer scripting or direct CLI commands, Alexandria supports flags for all major actions:

#### Movies
```bash
# Search for a film across all providers
python run.py --movie "Spirited Away"
python run.py --movie "Night of the Living Dead"

# Browse curated movie collections
python run.py --browse-movies feature_films
python run.py --browse-movies SciFi_Horror
python run.py --browse-movies Film_Noir
python run.py --browse-movies Comedy_Films

# Download directly by URL or Archive identifier
python run.py --movie "https://archive.org/details/Night.Of.The.Living.Dead_1080p"

# Play a downloaded movie with automatic progress tracking
python run.py --play-movie "Spirited Away"
```

#### Anime
```bash
# Search and download anime series
python run.py --anime "Hunter x Hunter"

# Download a specific series URL at 1080p
python run.py --anime "https://hianime.to/hunter-x-hunter-128" --quality 1080p

# Browse popular anime or by alphabet letter
python run.py --browse-anime popular
python run.py --browse-anime N

# Resume or watch an anime series
python run.py --play-anime "Hunter x Hunter (2011)"
```

#### TV Shows
```bash
# Search TV series and view episode guides
python run.py --tv "Breaking Bad"

# Play a downloaded TV episode
python run.py --play-tv "Breaking Bad"
```

#### Progress & Library Management
```bash
# View all series, movie runtimes, and watched episode percentages
python run.py --progress
```

---

## Setting Your Download Folder & Jellyfin Integration

By default, Alexandria creates a `media/` folder inside its working directory. You can easily point it to your external drive or directly to your existing Jellyfin media directory.

### Set the Download Folder
```bash
# Point to your primary media drive
python run.py --set-download-dir "D:\Jellyfin\Media"

# Or point directly to a dedicated library (e.g. Movies only)
python run.py --set-download-dir "D:\Jellyfin\Movies"
```

### Open the Folder in File Explorer
```bash
# Opens whatever folder is currently configured in Windows Explorer / macOS Finder / Linux file manager
python run.py --open-folder
```

### Check Current Configuration
```bash
python run.py --config
```

### How Alexandria Organizes Your Files

When downloads finish, files are placed into clean directories following standard media server standards:

```text
media/
├── anime/
│   └── Hunter x Hunter (2011)/
│       └── Season 01/
│           └── Hunter x Hunter (2011) - S01E01.mp4
├── tv/
│   └── Breaking Bad (2008)/
│       └── Season 01/
│           └── Breaking Bad (2008) - S01E01.mp4
└── movies/
    └── Spirited Away (2001)/
        └── Spirited Away (2001).mp4
```

If you configure your path directly to a dedicated folder like `D:\Jellyfin\Movies`, Alexandria recognizes that you are already inside a Movies library and saves movies straight into `D:\Jellyfin\Movies\<Title> (<Year>)` without adding unnecessary subfolders.

---

## Building from Source

To compile your own standalone single-file `alexandria.exe`:

```bash
# Install PyInstaller
pip install pyinstaller

# Run the build
python -m PyInstaller --noconfirm --clean --onefile --name alexandria --add-data "providers/tokyoinsider_catalog.json;providers" --collect-submodules providers --collect-submodules kitsu --hidden-import requests --hidden-import urllib3 --hidden-import bs4 --hidden-import tqdm run.py
```

The compiled binary will be placed inside `dist/alexandria.exe`.

---

## Project Structure

```text
alexandria/
├── run.py                 # Main CLI launcher and argument parser
├── cli.py                 # Interactive terminal dashboard, menus, and player launcher
├── config.py              # Path resolver, Jellyfin integration, persistent settings
├── scraper.py             # Media orchestrator connecting providers and downloader
├── progress.py            # Local progress database and resume tracking
├── providers/             # Provider backends
│   ├── movies.py          # Feature films, anime movies, Archive.org cinema
│   ├── hianime.py         # HiAnime scraper and sliding-window HLS downloader
│   ├── tokyoinsider.py    # TokyoInsider scraper and stream decoder
│   ├── tvshows.py         # TVMaze metadata provider
│   └── manager.py         # Provider registry and routing
├── kitsu/                 # Kitsu API client for Japanese title aliases
├── tests/                 # Automated smoke tests
├── .github/workflows/     # CI pipeline testing on Ubuntu, Windows, and macOS
├── LICENSE                # MIT License
└── README.md              # Project documentation
```

---

## Running Tests

Run the test suite using pytest:

```bash
pytest
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
