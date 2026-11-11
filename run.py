"""
Entry point for Alexandria - High-Performance Anime, TV & Movie Streaming Media Studio.
"""
import os
import sys
from cli import parse_cli_args, main_menu, print_banner
from scraper import MediaScraper

def main():
    args = parse_cli_args()

    scraper = MediaScraper(output_dir=args.output_dir)

    if args.browse_anime:
        print_banner()
        from cli import interactive_browse_anime
        val = args.browse_anime.strip() if args.browse_anime else "popular"
        category = "popular"
        letter = None
        if val.lower() in ["popular", "new", "list"]:
            category = val.lower()
        elif len(val) == 1:
            category = "list"
            letter = val.upper()
        interactive_browse_anime(scraper, initial_category=category, initial_letter=letter)
        return

    if args.anime:
        print_banner()
        target = args.anime.strip()
        if "tokyoinsider.com" in target or "hianime" in target or "/anime/" in target or target.startswith("http"):
            from cli import prompt_and_download_anime
            prompt_and_download_anime(scraper, target)
        else:
            print(f"Searching anime series across providers for '{target}'...")
            results = scraper.search_anime(target, limit=20)
            if not results:
                print("No anime series found matching query.")
            else:
                for idx, r in enumerate(results, 1):
                    p_badge = "[HiAnime]" if r.get("provider") == "hianime" else f"[{r.get('letter', 'TI')}]"
                    print(f"[{idx:2d}] {p_badge:<11} {r['title']} ({r.get('slug')})")
                from cli import prompt_int, prompt_and_download_anime
                choice = prompt_int(f"\nChoose anime to inspect / download [1-{len(results)}] or [0] to exit", min_val=0, max_val=len(results), default=0)
                if choice > 0:
                    prompt_and_download_anime(scraper, results[choice - 1])
        return

    if args.play_anime is not None:
        print_banner()
        from cli import interactive_play_anime, _play_episode_from_folder, get_anime_series_folder
        if args.play_anime:
            series_path = get_anime_series_folder(scraper, args.play_anime)
            if os.path.isdir(series_path):
                _play_episode_from_folder(series_path)
            else:
                interactive_play_anime(scraper)
        else:
            interactive_play_anime(scraper)
        return

    if getattr(args, 'tv', None):
        print_banner()
        target = args.tv.strip()
        print(f"Searching TVMaze for TV show '{target}'...")
        results = scraper.search_tv_shows(target, limit=15)
        if not results:
            print("No TV shows found matching query on TVMaze.")
        else:
            for idx, r in enumerate(results, 1):
                yr = f" ({r['year']})" if r.get('year') else ""
                net = f" [{r['network']}]" if r.get('network') else ""
                rat = f" [Rating: {r['rating']}]" if r.get('rating') and r['rating'] != 'N/A' else ""
                print(f"[{idx:2d}] {r['title']}{yr}{net}{rat}")
            from cli import prompt_int, _inspect_tv_show_dialog
            choice = prompt_int(f"\nChoose TV show to inspect / manage [1-{len(results)}] or [0] to exit", min_val=0, max_val=len(results), default=0)
            if choice > 0:
                _inspect_tv_show_dialog(scraper, results[choice - 1]["id"])
        return

    if getattr(args, 'play_tv', None) is not None:
        print_banner()
        from cli import interactive_play_tv, _play_episode_from_folder, get_tv_series_folder
        if args.play_tv:
            series_path = get_tv_series_folder(scraper, args.play_tv)
            if os.path.isdir(series_path):
                _play_episode_from_folder(series_path)
            else:
                interactive_play_tv(scraper)
        else:
            interactive_play_tv(scraper)
        return

    if getattr(args, 'browse_movies', None):
        print_banner()
        from cli import _browse_archive_movies_dialog
        _browse_archive_movies_dialog(scraper)
        return

    if getattr(args, 'movie', None):
        print_banner()
        target = args.movie.strip()
        from cli import prompt_and_download_movie
        if target.startswith("http") or "/details/" in target:
            prompt_and_download_movie(scraper, target)
        else:
            print(f"Searching movies across providers for '{target}'...")
            results = scraper.search_movies(target, limit=20)
            if not results:
                print("No movies found matching query.")
            else:
                for idx, r in enumerate(results, 1):
                    p_badge = "[HiAnime]" if r.get("provider") == "hianime" else ("[TI]" if r.get("provider") == "tokyoinsider" else "[Archive]")
                    yr = f" ({r['year']})" if r.get('year') else ""
                    tag = f" [{r.get('voice_tag')}]" if r.get('voice_tag') else ""
                    print(f"[{idx:2d}] {p_badge:<11} {r['title']}{yr}{tag}")
                from cli import prompt_int
                choice = prompt_int(f"\nChoose movie to inspect / download [1-{len(results)}] or [0] to exit", min_val=0, max_val=len(results), default=0)
                if choice > 0:
                    prompt_and_download_movie(scraper, results[choice - 1])
        return

    if getattr(args, 'play_movie', None) is not None:
        print_banner()
        from cli import interactive_play_movie, _play_episode_from_folder, get_movie_folder
        if args.play_movie:
            movie_path = get_movie_folder(scraper, args.play_movie)
            if os.path.isdir(movie_path):
                _play_episode_from_folder(movie_path)
            else:
                interactive_play_movie(scraper)
        else:
            interactive_play_movie(scraper)
        return

    if args.progress:
        print_banner()
        import os
        import re
        import progress

        out_dir = args.output_dir
        for candidate in ["Book_Files", "book_files"]:
            if os.path.isdir(candidate):
                out_dir = candidate
                break

        if not os.path.isdir(out_dir):
            print(f"[!] No library directory found at '{out_dir}'.")
            return

        items = []
        seen_paths = set()

        # 1. Anime Series
        for a_root in [os.path.join(out_dir, "anime"), "anime_files"]:
            if not os.path.isdir(a_root):
                continue
            for d in sorted(os.listdir(a_root)):
                s_path = os.path.join(a_root, d)
                if not os.path.isdir(s_path) or s_path in seen_paths:
                    continue
                vids = []
                for r_dir, _, files in os.walk(s_path):
                    for f in files:
                        if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')) and not f.endswith(".part"):
                            vids.append(f)
                if vids:
                    seen_paths.add(s_path)
                    items.append({
                        "title": d,
                        "path": s_path,
                        "type": "anime",
                        "info": f"{len(vids)} episodes [Jellyfin]"
                    })

        # 2. TV Series
        for t_root in [os.path.join(out_dir, "tv"), "tv_files", "shows"]:
            if not os.path.isdir(t_root):
                continue
            for d in sorted(os.listdir(t_root)):
                s_path = os.path.join(t_root, d)
                if not os.path.isdir(s_path) or s_path in seen_paths:
                    continue
                vids = []
                for r_dir, _, files in os.walk(s_path):
                    for f in files:
                        if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')) and not f.endswith(".part"):
                            vids.append(f)
                if vids:
                    seen_paths.add(s_path)
                    items.append({
                        "title": d,
                        "path": s_path,
                        "type": "tv",
                        "info": f"{len(vids)} episodes [Jellyfin]"
                    })

        # 3. Movie Folders
        for m_root in [os.path.join(out_dir, "movies"), "movie_files", "movies"]:
            if not os.path.isdir(m_root):
                continue
            for d in sorted(os.listdir(m_root)):
                s_path = os.path.join(m_root, d)
                if not os.path.isdir(s_path) or s_path in seen_paths:
                    continue
                vids = []
                for r_dir, _, files in os.walk(s_path):
                    for f in files:
                        if f.lower().endswith(('.mp4', '.mkv', '.avi', '.webm')) and not f.endswith(".part"):
                            vids.append(os.path.join(r_dir, f))
                if vids:
                    seen_paths.add(s_path)
                    sz_mb = os.path.getsize(vids[0]) / (1024 * 1024)
                    sz_str = f"{sz_mb / 1024:.2f} GB" if sz_mb >= 1024 else f"{sz_mb:.0f} MB"
                    items.append({
                        "title": d,
                        "path": s_path,
                        "type": "movie",
                        "info": f"Feature Film ({sz_str}) [Jellyfin]"
                    })

        if not items:
            print(f"No series or movies downloaded yet in '{out_dir}'.")
            return

        print("Alexandria Library & Progress Overview:")
        print("-" * 75)
        for item in items:
            s_path = item["path"]
            m_type = item["type"]
            tag = "[Anime]  " if m_type == "anime" else ("[TV Show]" if m_type == "tv" else "[Movie]  ")
            print(f"{tag} Series: {item['title']} ({item['info']})")

            w = progress.get_watch_progress(s_path)
            if m_type == "movie":
                if w:
                    pos = w.get("position_sec")
                    dur = w.get("duration_sec")
                    pct = w.get("percent", 0.0)
                    if w.get("status") == "completed" or pct >= 95.0:
                        print("  Status:   Fully Watched (100%)")
                    elif pos and dur:
                        pos_s = progress.format_seconds(pos)
                        dur_s = progress.format_seconds(dur)
                        print(f"  Resume:   {pos_s} / {dur_s} ({pct:.1f}%)")
                    else:
                        print(f"  Progress: {pct:.1f}%")
                else:
                    print("  Status:   Unwatched")
                print("  Format:   High-Res Movie (.mp4) [Jellyfin]")
                print()
                continue

            watched_eps = progress.get_watched_episodes(s_path)
            m_cnt = re.search(r'(\d+)', item['info'])
            tot_vids = int(m_cnt.group(1)) if m_cnt else 1
            w_cnt = len(watched_eps)
            pct = round((w_cnt / max(1, tot_vids)) * 100.0, 1)
            all_eps = progress.get_all_episodes_detail(s_path)
            in_prog_ep = None
            for ep_name, ep_data in all_eps.items():
                if ep_data.get("status") == "in_progress" and ep_data.get("position_sec"):
                    in_prog_ep = (ep_name, ep_data)
                    break

            if w:
                last_ep = w.get("episode_title") or w.get("rel_path") or ""
                print(f"  Watching: {w_cnt}/{tot_vids} episodes watched ({pct}%)")
                if in_prog_ep:
                    name, d = in_prog_ep
                    pos_str = progress.format_seconds(d.get("position_sec", 0))
                    dur_str = progress.format_seconds(d.get("duration_sec", 0)) if d.get("duration_sec") else "?"
                    print(f"  Resume:   {name} ({pos_str} / {dur_str}, {d.get('percent', 0):.1f}%)")
                elif last_ep:
                    print(f"  Last:     {last_ep}")
            elif w_cnt > 0:
                print(f"  Watching: {w_cnt}/{tot_vids} episodes watched ({pct}%)")
            else:
                print("  Watching: Not started")
            print("  Format:   High-Res Video (.mp4 / .mkv) [Jellyfin]")
            print()
        return

    # Default to interactive menu
    main_menu()

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\nExiting Alexandria. Goodbye!\n")
        sys.exit(0)
