import os
import json
import time
from typing import Optional, Callable, Dict, Any, List, Tuple
from tqdm import tqdm

from providers.manager import ProviderManager
import config

class MediaScraper:
    """Universal anime, television, and movie media orchestrator for Alexandria."""

    def __init__(self, output_dir: Optional[str] = None):
        if not output_dir:
            self.output_dir = config.get_download_dir()
        else:
            self.output_dir = config.sanitize_input_path(output_dir)
        os.makedirs(self.output_dir, exist_ok=True)
        self.providers = ProviderManager()

    def get_media_dir(self, media_type: str) -> str:
        """Returns the resolved Jellyfin directory for the requested media type."""
        return config.get_media_dir(media_type, self.output_dir)

    def resolve_jellyfin_paths(self) -> Dict[str, Any]:
        """Returns the resolved Jellyfin library subfolder mapping."""
        return config.resolve_jellyfin_paths(self.output_dir)

    def search_anime(self, query: str, limit: int = 20, provider: str = "all") -> List[Dict[str, Any]]:
        """Search anime series across HiAnime and TokyoInsider."""
        return self.providers.search_anime(query, limit=limit, provider=provider)

    def browse_anime(
        self,
        category: str = "popular",
        letter: Optional[str] = None,
        page_num: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Browse anime series by popular, new, or A-Z index."""
        return self.providers.browse_anime(category=category, letter=letter, page_num=page_num, limit=limit)

    def get_anime_details(self, slug_or_url: str, provider: str = "auto") -> Dict[str, Any]:
        """Fetch complete anime series metadata and episode listing."""
        return self.providers.get_anime_details(slug_or_url, provider=provider)

    def download_anime(
        self,
        slug_or_url: str,
        start_ep: int = 1,
        end_ep: Optional[int] = None,
        quality: str = "best",
        language: str = "english",
        voice_pref: str = "dub",
        strict_voice: bool = False,
        output_dir: Optional[str] = None,
        overwrite: bool = False,
        delay: float = 0.5,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        provider: str = "auto"
    ) -> Dict[str, Any]:
        """Download anime episodes in standard Jellyfin directory layout."""
        target_dir = output_dir or config.get_media_dir("anime", self.output_dir)

        return self.providers.download_anime(
            slug_or_url,
            start_ep=start_ep,
            end_ep=end_ep,
            quality=quality,
            language=language,
            voice_pref=voice_pref,
            strict_voice=strict_voice,
            output_dir=target_dir,
            overwrite=overwrite,
            delay=delay,
            progress_callback=progress_callback,
            provider=provider
        )

    def search_tv_shows(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search television series via TVMaze."""
        return self.providers.search_tv_shows(query, limit=limit)

    def get_show_details(self, show_id: int) -> Dict[str, Any]:
        """Fetch TV show details and complete episode guides."""
        return self.providers.get_show_details(show_id)

    def download_tv_episode(
        self,
        media_url: str,
        series_title: str,
        season_num: int,
        ep_num: int,
        ep_title: str,
        year: Optional[str] = None,
        output_dir: Optional[str] = None,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> bool:
        """Download a TV show episode in standard Jellyfin directory layout."""
        target_dir = output_dir or config.get_media_dir("tv", self.output_dir)
        return self.providers.download_tv_episode(
            media_url,
            series_title,
            season_num,
            ep_num,
            ep_title,
            year=year,
            output_dir=target_dir,
            progress_callback=progress_callback
        )

    def search_movies(self, query: str, limit: int = 25, provider: str = "all") -> List[Dict[str, Any]]:
        """Search movies across HiAnime, TokyoInsider, and Internet Archive Cinema."""
        return self.providers.search_movies(query, limit=limit, provider=provider)

    def browse_movies(self, collection: str = "feature_films", limit: int = 25) -> List[Dict[str, Any]]:
        """Browse classic feature films, horror, sci-fi, and film noir on Internet Archive."""
        return self.providers.browse_movies(collection=collection, limit=limit)

    def get_archive_movie_files(self, identifier: str) -> List[Dict[str, Any]]:
        """Fetch direct video MP4 download links for an Archive.org movie."""
        return self.providers.get_archive_movie_files(identifier)

    def download_movie(
        self,
        movie_target: Any,
        quality: str = "best",
        voice_pref: str = "dub",
        strict_voice: bool = False,
        output_dir: Optional[str] = None,
        overwrite: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """Download a movie in Jellyfin format with container repair."""
        target_dir = output_dir or config.get_media_dir("movie", self.output_dir)
        return self.providers.download_movie(
            movie_target,
            quality=quality,
            voice_pref=voice_pref,
            strict_voice=strict_voice,
            output_dir=target_dir,
            overwrite=overwrite,
            progress_callback=progress_callback
        )
