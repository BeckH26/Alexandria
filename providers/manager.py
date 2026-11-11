import os
import re
from typing import List, Dict, Any, Optional, Callable

from .tokyoinsider import TokyoInsiderProvider
from .hianime import HiAnimeProvider
from .tvshows import TVShowProvider
from .movies import MovieProvider

class ProviderManager:
    """
    Unified manager for anime, television, and movie media providers for Alexandria.
    Provides multi-source searching across HiAnime, TokyoInsider, TVMaze, and Internet Archive.
    """

    def __init__(self):
        self._tokyoinsider = None
        self._hianime = None
        self._tvshows = None
        self._movies = None

    @property
    def movies(self) -> MovieProvider:
        """Lazy-loaded MovieProvider for feature films, classic cinema, and anime movies."""
        if self._movies is None:
            self._movies = MovieProvider()
        return self._movies

    @property
    def hianime(self) -> HiAnimeProvider:
        """Lazy-loaded HiAnime provider for English Dub & Sub anime streaming & downloads."""
        if self._hianime is None:
            self._hianime = HiAnimeProvider()
        return self._hianime

    @property
    def tvshows(self) -> TVShowProvider:
        """Lazy-loaded TVShowProvider for television series metadata and Jellyfin downloads."""
        if self._tvshows is None:
            self._tvshows = TVShowProvider()
        return self._tvshows

    @property
    def tokyoinsider(self) -> TokyoInsiderProvider:
        """Lazy-loaded TokyoInsider provider for anime series and high-res video streaming."""
        if self._tokyoinsider is None:
            self._tokyoinsider = TokyoInsiderProvider()
        return self._tokyoinsider

    def search_anime(self, query: str, limit: int = 20, provider: str = "all") -> List[Dict[str, Any]]:
        """
        Searches anime series across providers, prioritizing HiAnime English Dub releases,
        with automated fallback to TokyoInsider.
        """
        combined = []
        seen_keys = set()

        # 1. Search HiAnime
        if provider in ("all", "hianime"):
            try:
                hi_results = self.hianime.search(query, limit=limit)
                for r in hi_results:
                    key = re.sub(r'[^a-zA-Z0-9]', '', (r.get("raw_title") or r["title"]).lower())
                    if key not in seen_keys:
                        seen_keys.add(key)
                        combined.append(r)
            except Exception:
                pass

        # 2. Search TokyoInsider
        if provider in ("all", "tokyoinsider"):
            try:
                ti_results = self.tokyoinsider.search(query, limit=limit)
                for r in ti_results:
                    key = re.sub(r'[^a-zA-Z0-9]', '', r["title"].lower())
                    if key not in seen_keys:
                        seen_keys.add(key)
                        combined.append(r)
            except Exception:
                pass

        return combined[:limit]

    def browse_anime(
        self,
        category: str = "popular",
        letter: Optional[str] = None,
        page_num: int = 1,
        limit: int = 20
    ) -> List[Dict[str, Any]]:
        """Browse anime catalog by popularity, new releases, or A-Z letter index."""
        return self.tokyoinsider.browse(category=category, letter=letter, page_num=page_num, limit=limit)

    def get_anime_details(self, slug_or_url: str, provider: str = "auto") -> Dict[str, Any]:
        """Fetch complete anime series metadata and episode guides."""
        s = str(slug_or_url).strip()
        p = provider.lower().strip()
        if p == "hianime" or "hianime" in s or (re.search(r'-(\d+)$', s.rstrip('/')) and "/" not in s.strip('/\\')):
            return self.hianime.get_anime_details(s)
        return self.tokyoinsider.get_anime_details(s)

    def download_anime(
        self,
        slug_or_url: str,
        start_ep: int = 1,
        end_ep: Optional[int] = None,
        quality: str = "best",
        language: str = "english",
        voice_pref: str = "dub",
        strict_voice: bool = False,
        output_dir: str = "Book_Files/anime",
        overwrite: bool = False,
        delay: float = 0.5,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None,
        provider: str = "auto"
    ) -> Dict[str, Any]:
        """Download anime episodes from HiAnime or TokyoInsider in Jellyfin format."""
        s = str(slug_or_url).strip()
        p = provider.lower().strip()
        if p == "hianime" or "hianime" in s or (re.search(r'-(\d+)$', s.rstrip('/')) and "/" not in s.strip('/\\')):
            return self.hianime.download_anime(
                s,
                start_ep=start_ep,
                end_ep=end_ep,
                quality=quality,
                language=language,
                voice_pref=voice_pref,
                strict_voice=strict_voice,
                output_dir=output_dir,
                overwrite=overwrite,
                delay=delay,
                progress_callback=progress_callback
            )
        return self.tokyoinsider.download_anime(
            s,
            start_ep=start_ep,
            end_ep=end_ep,
            quality=quality,
            language=language,
            voice_pref=voice_pref,
            strict_voice=strict_voice,
            output_dir=output_dir,
            overwrite=overwrite,
            delay=delay,
            progress_callback=progress_callback
        )

    def search_tv_shows(self, query: str, limit: int = 20) -> List[Dict[str, Any]]:
        """Search television series via TVMaze."""
        results = self.tvshows.search(query)
        return results[:limit] if limit else results

    def get_show_details(self, show_id: int) -> Dict[str, Any]:
        """Fetch TV show metadata and complete season/episode list."""
        return self.tvshows.get_show_details(show_id)

    def download_tv_episode(
        self,
        media_url: str,
        series_title: str,
        season_num: int,
        ep_num: int,
        ep_title: str,
        year: Optional[str] = None,
        output_dir: str = "Book_Files/tv",
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> bool:
        """Download a TV show episode in standard Jellyfin directory layout."""
        return self.tvshows.download_tv_episode(
            media_url,
            series_title,
            season_num,
            ep_num,
            ep_title,
            year=year,
            output_dir=output_dir,
            progress_callback=progress_callback
        )

    def search_movies(self, query: str, limit: int = 25, provider: str = "all") -> List[Dict[str, Any]]:
        """Search movies across HiAnime, TokyoInsider, and Internet Archive Cinema."""
        return self.movies.search_movies(query, limit=limit, provider=provider)

    def browse_movies(self, collection: str = "feature_films", limit: int = 25) -> List[Dict[str, Any]]:
        """Browse classic feature films, horror, sci-fi, and film noir on Internet Archive."""
        return self.movies.browse_archive_movies(collection=collection, limit=limit)

    def get_archive_movie_files(self, identifier: str) -> List[Dict[str, Any]]:
        """Fetch direct video MP4 download links for an Archive.org movie."""
        return self.movies.get_archive_movie_files(identifier)

    def download_movie(
        self,
        movie_target: Any,
        quality: str = "best",
        voice_pref: str = "dub",
        strict_voice: bool = False,
        output_dir: str = "Book_Files",
        overwrite: bool = False,
        progress_callback: Optional[Callable[[Dict[str, Any]], None]] = None
    ) -> Dict[str, Any]:
        """Download a movie in Jellyfin format with container repair."""
        return self.movies.download_movie(
            movie_target,
            quality=quality,
            voice_pref=voice_pref,
            strict_voice=strict_voice,
            output_dir=output_dir,
            overwrite=overwrite,
            progress_callback=progress_callback
        )
