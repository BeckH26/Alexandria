"""
Alexandria Smoke and Integration Test Suite
Validates core interfaces, provider instantiation, CLI argument parsing,
title relevance matching, Jellyfin folder structures, and watch progress database operations.
"""

import os
import sys
import tempfile
import pytest

# Ensure local repository root is on sys.path
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if REPO_ROOT not in sys.path:
    sys.path.insert(0, REPO_ROOT)

import cli
import progress
import scraper
import run
from providers.manager import ProviderManager
from providers.movies import MovieProvider, is_title_relevant, get_jellyfin_movie_path, ARCHIVE_COLLECTIONS


class TestModuleImports:
    """Validate that all core modules import without runtime or dependency errors."""

    def test_core_imports(self):
        assert cli is not None
        assert progress is not None
        assert scraper is not None
        assert run is not None

    def test_provider_imports(self):
        from providers import (
            ProviderManager,
            HiAnimeProvider,
            TokyoInsiderProvider,
            TVShowProvider,
            MovieProvider,
        )
        assert ProviderManager is not None
        assert HiAnimeProvider is not None
        assert TokyoInsiderProvider is not None
        assert TVShowProvider is not None
        assert MovieProvider is not None

    def test_kitsu_import(self):
        from kitsu import KitsuClient
        assert KitsuClient is not None


class TestProviderManager:
    """Validate ProviderManager lifecycle and lazy loading."""

    def test_lazy_loaded_providers(self):
        manager = ProviderManager()
        assert manager._movies is None
        assert manager._hianime is None
        assert manager._tvshows is None
        assert manager._tokyoinsider is None

        # Access properties to trigger lazy instantiation
        assert isinstance(manager.movies, MovieProvider)
        assert manager._movies is not None

        assert manager.hianime is not None
        assert manager.tvshows is not None
        assert manager.tokyoinsider is not None


class TestTitleRelevanceFilter:
    """Validate title relevance heuristic for eliminating false positives."""

    def test_positive_matches(self):
        assert is_title_relevant("Spirited Away", "Spirited Away (Movie)")
        assert is_title_relevant("Akira", "Akira 1988 Remastered")
        assert is_title_relevant("Night of the Living Dead", "Night of the Living Dead (1968)")
        assert is_title_relevant("Nosferatu", "Nosferatu: A Symphony of Horror (1922)")

    def test_negative_matches(self):
        assert not is_title_relevant("Spirited Away", "Completely Unrelated Film Title")
        assert not is_title_relevant("Avatar: The Way of Water", "The Great Train Robbery (1903)")
        assert not is_title_relevant("Dune: Part Two", "Random Podcast Episode 42")
        assert not is_title_relevant("Non-Existent Query 9999", "Classic Western Movie")


class TestArchiveCollections:
    """Verify archive collections map to valid non-empty keys."""

    def test_collection_keys(self):
        expected_keys = ["feature_films", "SciFi_Horror", "Film_Noir", "Comedy_Films", "silent_films"]
        for key in expected_keys:
            assert key in ARCHIVE_COLLECTIONS
            assert len(ARCHIVE_COLLECTIONS[key]) > 0


class TestJellyfinNaming:
    """Verify Jellyfin path and folder naming computations."""

    def test_movie_path_computation(self):
        folder, filename = get_jellyfin_movie_path("Spirited Away", "2001")
        assert folder == "Spirited Away (2001)"
        assert filename == "Spirited Away (2001).mp4"

        # Embedded year extraction
        folder2, filename2 = get_jellyfin_movie_path("Metropolis (1927)")
        assert folder2 == "Metropolis (1927)"
        assert filename2 == "Metropolis (1927).mp4"


class TestProgressTracker:
    """Verify watch progress tracking and persistence."""

    def test_watch_progress_lifecycle(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            series_dir = os.path.join(tmpdir, "Metropolis (1927)")
            os.makedirs(series_dir, exist_ok=True)
            video_file = os.path.join(series_dir, "Metropolis (1927).mp4")

            # Save progress for a test movie
            progress.save_watch_progress(
                series_dir=series_dir,
                episode_file=video_file,
                episode_title="Metropolis (1927)",
                total_episodes=1,
                media_type="movie",
                mark_completed=False,
                position_sec=1200.0,
                duration_sec=5400.0
            )

            # Load progress back
            data = progress.load_series_progress(series_dir)
            assert data is not None
            assert "watch" in data
            assert data["watch"] is not None
            watch_data = data["watch"]
            assert "episodes" in watch_data
            assert "Metropolis (1927).mp4" in watch_data["episodes"]
            ep_data = watch_data["episodes"]["Metropolis (1927).mp4"]
            assert ep_data.get("position_sec") == 1200.0
            assert ep_data.get("duration_sec") == 5400.0
            assert ep_data.get("percent") == pytest.approx(22.2, rel=1e-1)


class TestMediaScraper:
    """Verify MediaScraper initialization and provider binding."""

    def test_scraper_init(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            ms = scraper.MediaScraper(output_dir=tmpdir)
            assert os.path.exists(tmpdir)
            assert ms.providers is not None
            assert hasattr(ms, "search_movies")
            assert hasattr(ms, "browse_movies")
            assert hasattr(ms, "search_anime")
            assert hasattr(ms, "search_tv_shows")


class TestConfigAndJellyfinIntegration:
    """Verify persistent download directory configuration and Jellyfin path resolution."""

    def test_default_download_dir(self):
        import config
        d = config.get_download_dir()
        assert isinstance(d, str)
        assert len(d) > 0

    def test_resolve_jellyfin_root(self):
        import config
        paths = config.resolve_jellyfin_paths(r"C:\Media\Jellyfin")
        assert paths["root"] == os.path.abspath(r"C:\Media\Jellyfin")
        assert paths["movie"].endswith("movies") or paths["movie"].endswith("Movies")
        assert paths["tv"].endswith("tv") or paths["tv"].endswith("TV") or "shows" in paths["tv"].lower()
        assert paths["anime"].endswith("anime") or paths["anime"].endswith("Anime")
        assert paths["is_dedicated_library"] is False

    def test_resolve_jellyfin_dedicated_movies(self):
        import config
        paths = config.resolve_jellyfin_paths(r"C:\Media\Jellyfin\Movies")
        assert paths["is_dedicated_library"] is True
        assert paths["dedicated_type"] == "movie"
        assert paths["movie"] == os.path.abspath(r"C:\Media\Jellyfin\Movies")

    def test_resolve_jellyfin_dedicated_tv(self):
        import config
        paths = config.resolve_jellyfin_paths(r"C:\Media\Jellyfin\TV Shows")
        assert paths["is_dedicated_library"] is True
        assert paths["dedicated_type"] == "tv"
        assert paths["tv"] == os.path.abspath(r"C:\Media\Jellyfin\TV Shows")

    def test_set_download_dir_lifecycle(self):
        import config
        with tempfile.TemporaryDirectory() as tmpdir:
            ok, msg, paths = config.set_download_dir(tmpdir)
            assert ok is True
            assert paths["root"] == os.path.abspath(tmpdir)
            assert config.get_download_dir() == os.path.abspath(tmpdir)

            # Clean up config file so other tests are not affected
            cfg_path = config.get_active_config_path()
            if os.path.exists(cfg_path):
                os.remove(cfg_path)

