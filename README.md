# Alexandria

A command-line tool for searching, downloading, and watching anime, movies, and TV shows.

Files are automatically saved in standard Jellyfin / Plex folder formats, and your watch progress is saved locally so you can resume where you stopped.

---

## Features

- **Anime**: Searches HiAnime and TokyoInsider. Supports selecting resolution (1080p, 720p, 480p) and voice preferences (sub or dub).
- **Movies**: Searches feature films from Internet Archive and anime movies from HiAnime and TokyoInsider.
- **TV Shows**: Searches show info and episode guides through TVMaze.
- **Jellyfin / Plex Organization**: Automatically saves files in standard library format (`Show (Year)/Season 01/Show - S01E01.mp4`). If pointed directly to an existing library folder, it saves files there without adding extra nested directories.
- **Watch History & Resume**: Tracks watched episodes and movies. Pressing `W` in the interactive menu resumes your last-watched item in your system video player (VLC, MPV, etc.).
- **Automatic Remuxing**: Stream chunks are converted into standard MP4 files via FFmpeg with fast-start headers for smooth seeking.

---

## Installation

### Windows (Pre-built Executable)
Download `alexandria.exe` from the [Releases](https://github.com/alexandria-media/alexandria/releases) page. You can run it directly from a terminal or by double-clicking it. No Python installation is needed.

### From Source (All Platforms)
Requires Python 3.10 or newer. FFmpeg is recommended for video remuxing.

```bash
git clone https://github.com/alexandria-media/alexandria.git
cd alexandria
pip install -r requirements.txt
```

To install it as a command on your system:
```bash
pip install -e .
```

---

## Usage

### Interactive Menu
Running the tool without flags opens an interactive menu:

```bash
python run.py
# Or with the executable:
alexandria.exe
```

From the menu, you can search titles, browse categories, set download directories, or press `W` to resume watching your latest series.

### Command Line Options

#### Movies
```bash
# Search for a movie
python run.py --movie "Spirited Away"

# Download from a direct URL or Archive.org identifier
python run.py --movie "https://archive.org/details/Night.Of.The.Living.Dead_1080p"

# Browse collections
python run.py --browse-movies feature_films

# Play a downloaded movie
python run.py --play-movie "Spirited Away"
```

#### Anime
```bash
# Search and download anime
python run.py --anime "Hunter x Hunter"

# Download a specific URL with preferred quality
python run.py --anime "https://hianime.to/hunter-x-hunter-128" --quality 1080p

# Browse popular anime or by letter
python run.py --browse-anime popular
python run.py --browse-anime N

# Play the next unwatched episode
python run.py --play-anime "Hunter x Hunter (2011)"
```

#### TV Shows
```bash
# Search TV shows
python run.py --tv "Breaking Bad"

# Play a downloaded TV episode
python run.py --play-tv "Breaking Bad"
```

#### Watch Progress
```bash
# Show watched status and episode completion across your library
python run.py --progress
```

---

## Download Directory & Jellyfin Setup

By default, files are saved in a `media/` folder inside the project directory.

You can change this to any folder on your computer or external drive:

```bash
# Set download directory
python run.py --set-download-dir "D:\Jellyfin\Media"

# Check current paths
python run.py --config

# Open the download folder in your file manager
python run.py --open-folder
```

### Folder Layout

Downloads are organized into standard media folders:

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

If you set your download path directly to a dedicated library (such as `D:\Jellyfin\Movies`), Alexandria detects that and places movie folders directly inside it rather than creating a nested `movies/` subfolder.

---

## Building the Executable

To build the standalone Windows `.exe` yourself:

```bash
pip install pyinstaller
python -m PyInstaller --noconfirm --clean --onefile --name alexandria --add-data "providers/tokyoinsider_catalog.json;providers" --collect-submodules providers --collect-submodules kitsu --hidden-import requests --hidden-import urllib3 --hidden-import bs4 --hidden-import tqdm run.py
```

The output file will be at `dist/alexandria.exe`.

---

## Testing

Run unit and integration tests with pytest:

```bash
pytest
```

---

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
