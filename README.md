# ALEXANDRIA

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

Alexandria is a high-performance, terminal-native media workstation for Anime, Television series, and Feature Films. It features multi-provider scraping across HiAnime, TokyoInsider, TVMaze, and Internet Archive, concurrent multi-threaded HLS downloading with automatic MPEG-TS to ISOBMFF MP4 remuxing, desktop video player integration with timestamp resume tracking, and automated Jellyfin library management.

Strictly zero emojis. 100% native CLI with interactive menus and real-time progress bars.

---

## Key Features

1. **Movie & Cinema Studio**:
   - **Anime Movies & Films**: Access thousands of full-length anime movies from HiAnime and TokyoInsider with dedicated English Dubs, Japanese audio with subtitles, and 1080p HLS streams.
   - **Feature Films & World Cinema**: Integration with Internet Archive for public domain feature films, classic Hollywood cinema, Film Noir, Sci-Fi & Horror classics, and silent era masterpieces.
   - **Direct Video Acquisition**: High-speed direct MP4 downloading with auto-resume, rolling throughput meters, and ETA estimation.
   - **Container Repair**: Automated FFmpeg remuxing with `+faststart` atom placement for zero-latency seeking in any media player.
   - **Curated Collections**: Browse curated collections including `feature_films`, `SciFi_Horror`, `Film_Noir`, `Comedy_Films`, and `silent_films`.

2. **Anime Studio**:
   - **HiAnime**: Multi-source scraping with prioritized English Dubs, multi-language subs, and direct 1080p/720p HLS video streams.
   - **TokyoInsider**: Access to thousands of anime series, movies, and OVAs with fan-sub catalog search and direct stream decoders.
   - Quality preference ranking: `1080p Full HD`, `720p HD`, `480p`, Dual Audio, English Sub, and English Dub.
   - Automated intelligent fallback: Language preference (1st) -> Voice preference (2nd) -> Quality (3rd) with closest available resolution.

3. **Television Shows Studio**:
   - Comprehensive metadata lookup, episode guides, broadcast network, and rating information powered by TVMaze.
   - Integration with Internet Archive for public domain, classic television broadcasts, and direct video acquisition.
   - Direct episode and season URL downloading.

4. **High-Speed Sliding-Window HLS Downloader & Remuxer**:
   - Multi-threaded chunk downloading with concurrency controls to prevent Cloudflare IP rate-limiting.
   - Real-time rolling throughput speed measurement and ETA calculation in progress bars.
   - Deadlock-free sliding-window disk writer ensuring zero memory accumulation.
   - Automatic post-download container repair: trans-multiplexes raw transport streams (`.ts`) into valid ISOBMFF MP4 containers with `+faststart` metadata placement via FFmpeg. Eliminates media player stutter and `0x80070323` playback errors.

5. **Jellyfin Media Server Standard Compliance**:
   - Automatically organizes all downloaded anime, television, and movie media into Jellyfin-compliant directory hierarchies:
     ```text
     Book_Files/
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

6. **Desktop Video Playback with Resume Tracking**:
   - Launches native system video player (`os.startfile` on Windows, `open` on macOS, `xdg-open` on Linux).
   - Automatically tracks watched episodes and movies, timestamps, runtime completion percentage, and last-watched positions.
   - Quick 1-click resume from the main menu (press `W` to instantly resume the next unwatched episode or in-progress movie).
   - Media management dashboard: toggle individual watched status (`M`), mark all as watched (`A`), or clear history (`C`).

---

## Installation

### Prerequisites
- Python 3.10 or newer
- FFmpeg (recommended for container optimization and remuxing; bundled fallback provided via `imageio-ffmpeg`)
- Standard desktop media player (MPV, VLC, or system default player)

### From Source
```bash
# Clone the repository
git clone https://github.com/alexandria-media/alexandria.git
cd alexandria

# Install dependencies
pip install -r requirements.txt

# Or install in editable mode with development tools
pip install -e ".[dev]"
```

---

## CLI Usage

### Interactive Menu
Launch the full interactive terminal interface:
```bash
python run.py
# Or using installed package script:
alexandria
```

### Search & Download Movies
```bash
# Search movies across all providers (HiAnime, TokyoInsider, Archive.org)
python run.py --movie "Spirited Away"
python run.py --movie "Night of the Living Dead"

# Browse classic cinema collections
python run.py --browse-movies feature_films
python run.py --browse-movies SciFi_Horror
python run.py --browse-movies Film_Noir
python run.py --browse-movies Comedy_Films
python run.py --browse-movies silent_films

# Download movie by direct URL or Archive identifier
python run.py --movie "https://archive.org/details/Night.Of.The.Living.Dead_1080p"
```

### Search & Download Anime
```bash
# Search anime series across all providers
python run.py --anime "Hunter x Hunter"

# Download anime series by direct URL or slug
python run.py --anime "https://hianime.to/hunter-x-hunter-128" --quality 1080p

# Browse anime catalog (popular, new, or alphabetical index)
python run.py --browse-anime popular
python run.py --browse-anime N
```

### Search & Download Television Shows
```bash
# Search television shows via TVMaze
python run.py --tv "Breaking Bad"
```

### Video Playback & Resume
```bash
# Open interactive player for a movie
python run.py --play-movie "Spirited Away"

# Open interactive player for an anime series
python run.py --play-anime "Hunter x Hunter (2011)"

# Open interactive player for a television show
python run.py --play-tv "Breaking Bad"
```

### Library & Watch Progress
```bash
# View complete watch history and progress overview across anime, tv, and movies
python run.py --progress
```

### Download Directory & Jellyfin Configuration
Alexandria allows you to set your media destination to any local, external, or network folder (including direct Jellyfin library paths) and open it from the CLI.

```bash
# Configure download directory to your Jellyfin media root
python run.py --set-download-dir "D:\Jellyfin\Media"

# Or configure directly to a dedicated library (e.g. Movies only)
python run.py --set-download-dir "D:\Jellyfin\Movies"

# Open configured download directory immediately in File Explorer / Finder
python run.py --open-folder

# View current configuration and resolved Jellyfin paths
python run.py --config
```

#### Jellyfin Auto-Detection
When you set Alexandria's download folder to your Jellyfin media directory:
1. **Unified Media Roots**: Automatically routes movies to `Movies/`, TV shows to `TV Shows/` (or `tv/`), and anime to `Anime/` without requiring manual folder management.
2. **Dedicated Libraries**: If you target a specific library folder (e.g. `D:\Jellyfin\Movies`), Alexandria detects this and places `<Movie Title> (<Year>)` folders directly inside it without creating redundant nested `movies/` subdirectories.
3. **Zero-Transcode Compatibility**: All downloads are formatted into standard Jellyfin naming structures and repaired with FFmpeg `+faststart` atoms for instant Direct Play without server-side transcoding lag.

---

## Architecture & Directory Structure

```text
alexandria/
├── run.py                 # Main CLI entrypoint
├── cli.py                 # Interactive terminal UI, video playback & menus
├── scraper.py             # MediaScraper orchestrator (Anime, TV & Movies)
├── progress.py            # Watch history and episode/movie progress tracker
├── providers/             # Media and streaming providers
│   ├── movies.py          # Dedicated Movie provider (HiAnime, Archive.org, TokyoInsider)
│   ├── hianime.py         # HiAnime extractor & HLS sliding-window downloader
│   ├── tokyoinsider.py    # TokyoInsider search & stream decoder
│   ├── tvshows.py         # TVMaze metadata & Internet Archive downloader
│   └── manager.py         # Multi-provider coordinator
├── kitsu/                 # Kitsu API client for Japanese title aliases
├── tests/                 # Automated smoke and integration tests
├── .github/
│   ├── workflows/ci.yml   # Multi-platform CI pipeline
│   └── ISSUE_TEMPLATE/    # Issue templates
├── pyproject.toml         # Modern packaging specification
├── setup.py               # Setuptools script
├── CHANGELOG.md           # Release history
├── CONTRIBUTING.md        # Contributor guidelines
├── LICENSE                # MIT License
└── README.md              # Project documentation
```

---

## Testing

Run the test suite using `pytest`:
```bash
pytest
# Or via python module:
python -m pytest
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
