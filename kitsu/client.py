import requests
from typing import List, Dict, Any, Optional

class KitsuClient:
    """Client for querying Kitsu API (anime, movies, OVAs, categories)."""

    BASE_URL = "https://kitsu.io/api/edge"
    HEADERS = {
        "Accept": "application/vnd.api+json",
        "Content-Type": "application/vnd.api+json",
        "User-Agent": "Alexandria/1.0"
    }

    _categories_cache: Optional[List[Dict[str, Any]]] = None

    def __init__(self, session: Optional[requests.Session] = None):
        self.session = session or requests.Session()

    def get_all_categories(self, refresh: bool = False) -> List[Dict[str, Any]]:
        """
        Fetch and cache all categories from Kitsu sorted by total media count.
        There are ~218 categories in total.
        """
        if self._categories_cache and not refresh:
            return self._categories_cache

        categories = []
        limit = 50
        offset = 0

        while True:
            params = {
                "page[limit]": limit,
                "page[offset]": offset,
                "sort": "-totalMediaCount"
            }
            try:
                resp = self.session.get(
                    f"{self.BASE_URL}/categories",
                    headers=self.HEADERS,
                    params=params,
                    timeout=10
                )
                if not resp.ok:
                    break
                data = resp.json().get("data", [])
                if not data:
                    break

                for item in data:
                    attrs = item.get("attributes", {})
                    categories.append({
                        "id": item.get("id"),
                        "title": attrs.get("title", ""),
                        "slug": attrs.get("slug", ""),
                        "description": attrs.get("description", "") or "",
                        "total_count": attrs.get("totalMediaCount", 0)
                    })

                if len(data) < limit:
                    break
                offset += limit
            except Exception:
                break

        if categories:
            self._categories_cache = categories
        return categories or (self._categories_cache or [])

    def search_categories(self, query: str) -> List[Dict[str, Any]]:
        """Filter categories by keyword."""
        all_cats = self.get_all_categories()
        q = query.strip().lower()
        if not q:
            return all_cats[:20]

        matches = []
        for cat in all_cats:
            if q in cat["title"].lower() or q in cat["slug"].lower() or q in cat["description"].lower():
                matches.append(cat)
        return matches

    def get_media_by_category(
        self,
        category_slug: Any,
        subtype: Optional[str] = None,
        limit: int = 15,
        offset: int = 0
    ) -> List[Dict[str, Any]]:
        """
        Fetch media items for a specific category or multiple categories.
        category_slug can be a single slug string or a list of category slug strings.
        """
        if isinstance(category_slug, (list, tuple)):
            cat_filter = ",".join(str(s).strip().lower() for s in category_slug if str(s).strip())
        else:
            cat_filter = str(category_slug).strip().lower()

        params = {
            "filter[categories]": cat_filter,
            "page[limit]": limit,
            "page[offset]": offset,
            "sort": "-userCount"
        }
        if subtype and subtype.lower() != "all":
            params["filter[subtype]"] = subtype.lower()

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/anime",
                headers=self.HEADERS,
                params=params,
                timeout=10
            )
            data = resp.json().get("data", []) if resp.ok else []

            results = []
            for item in data:
                attrs = item.get("attributes", {})
                titles = attrs.get("titles", {}) or {}
                abbrev = attrs.get("abbreviatedTitles", []) or []
                poster = attrs.get("posterImage", {}) or {}

                results.append({
                    "id": item.get("id"),
                    "canonical_title": attrs.get("canonicalTitle", ""),
                    "titles": titles,
                    "abbreviated_titles": abbrev,
                    "subtype": attrs.get("subtype", "unknown"),
                    "status": attrs.get("status", ""),
                    "synopsis": attrs.get("synopsis", "") or "",
                    "user_count": attrs.get("userCount", 0),
                    "poster_url": poster.get("small") or poster.get("original") or ""
                })
            return results
        except Exception:
            return []

    def search_media(
        self,
        query: str,
        subtype: Optional[str] = None,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """Search Kitsu media by text query across anime and media catalogs."""
        params = {
            "filter[text]": query,
            "page[limit]": limit
        }
        if subtype and subtype.lower() != "all":
            params["filter[subtype]"] = subtype.lower()

        try:
            resp = self.session.get(
                f"{self.BASE_URL}/anime",
                headers=self.HEADERS,
                params=params,
                timeout=10
            )
            data = resp.json().get("data", []) if resp.ok else []

            # If no anime results, check general manga/source catalog
            if not data:
                resp_alt = self.session.get(
                    f"{self.BASE_URL}/manga",
                    headers=self.HEADERS,
                    params=params,
                    timeout=10
                )
                data = resp_alt.json().get("data", []) if resp_alt.ok else []

            results = []
            for item in data:
                attrs = item.get("attributes", {})
                titles = attrs.get("titles", {}) or {}
                abbrev = attrs.get("abbreviatedTitles", []) or []
                poster = attrs.get("posterImage", {}) or {}

                results.append({
                    "id": item.get("id"),
                    "canonical_title": attrs.get("canonicalTitle", ""),
                    "titles": titles,
                    "abbreviated_titles": abbrev,
                    "subtype": attrs.get("subtype", "unknown"),
                    "status": attrs.get("status", ""),
                    "synopsis": attrs.get("synopsis", "") or "",
                    "user_count": attrs.get("userCount", 0),
                    "poster_url": poster.get("small") or poster.get("original") or ""
                })
            return results
        except Exception:
            return []

    @staticmethod
    def extract_search_keywords(item: Dict[str, Any]) -> List[str]:
        """
        Extract candidate title queries to search for this media title across providers.
        Returns a deduplicated list of search keywords.
        """
        candidates = []
        if item.get("canonical_title"):
            candidates.append(item["canonical_title"])

        titles = item.get("titles", {}) or {}
        for lang in ("en", "en_jp", "en_us"):
            val = titles.get(lang)
            if val and val not in candidates:
                candidates.append(val)

        for abbr in item.get("abbreviated_titles", []) or []:
            if abbr and abbr not in candidates:
                candidates.append(abbr)

        return candidates
