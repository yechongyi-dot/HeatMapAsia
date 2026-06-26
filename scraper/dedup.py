"""Deduplication logic for video search results."""


def deduplicate(videos: list[dict], key: str = "video_id") -> list[dict]:
    """Remove duplicate videos by a given key field.

    First occurrence wins (preserves order from earlier searches).
    """
    seen: set[str] = set()
    unique: list[dict] = []
    for v in videos:
        vid = str(v.get(key, ""))
        if vid and vid not in seen:
            seen.add(vid)
            unique.append(v)
    return unique
