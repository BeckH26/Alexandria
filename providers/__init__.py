"""
Alexandria Providers Package
High-performance streaming and scraping providers for Anime, Television, and Cinema.
"""

from .manager import ProviderManager
from .hianime import HiAnimeProvider
from .tokyoinsider import TokyoInsiderProvider
from .tvshows import TVShowProvider
from .movies import MovieProvider

__all__ = [
    "ProviderManager",
    "HiAnimeProvider",
    "TokyoInsiderProvider",
    "TVShowProvider",
    "MovieProvider",
]
