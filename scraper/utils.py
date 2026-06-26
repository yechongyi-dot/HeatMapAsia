"""Shared, region-aware utility functions for scrapers.

Parsing helpers (relative time, view counts) are region-agnostic. Title
filtering and language detection are driven by :data:`scraper.regions.REGIONS`,
so the same code recognises Japanese, Korean and English (Singapore) finance
titles depending on the ``region`` passed in.
"""

import re
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional

from .regions import REGIONS, DEFAULT_REGION, NEGATIVE_KEYWORDS

logger = logging.getLogger(__name__)
# Reference clock for relative-time math. All three target markets sit at
# UTC+8/+9; since age is computed as (now - published) with both sides
# timezone-aware, the exact offset is immaterial — we just need a fixed,
# tz-aware "now". JST is kept as that canonical reference.
JST = timezone(timedelta(hours=9))


# ── Two-tier title matching ──
#
#   • native_keywords — CJK (kana/kanji/Hangul) terms. CJK has no word
#     boundaries, so plain substring matching is both necessary and safe.
#   • latin_ci / latin_cs — Latin-script acronyms/words. Matched as *whole
#     tokens* (bounded by non-alphanumerics) so "PER" doesn't match inside
#     "per favore" and "FX" doesn't match inside "VFX". The collision-prone
#     ratios (PER/ROE/PBR) are matched case-SENSITIVELY (uppercase only).


def _token_regex(words: list[str], flags=0) -> "re.Pattern":
    """Compile an alternation matching any *word* as a whole token.

    A token is bounded on both sides by a non-alphanumeric character (or the
    string edge). Longer alternatives are tried first. An optional trailing
    plural "s" is tolerated so "REITs"/"Dividends" still match "REIT"/"dividend".
    """
    alts = "|".join(re.escape(w) for w in sorted(words, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alts})s?(?![A-Za-z0-9])", flags)


def _build_matchers() -> dict[str, dict]:
    """Precompile per-region matchers once at import time."""
    out: dict[str, dict] = {}
    for rid, cfg in REGIONS.items():
        latin_ci = cfg.get("latin_ci", [])
        latin_cs = cfg.get("latin_cs", [])
        out[rid] = {
            "native": cfg.get("native_keywords", []),
            "latin_ci_re": _token_regex(latin_ci, re.IGNORECASE) if latin_ci else None,
            "latin_cs_re": _token_regex(latin_cs) if latin_cs else None,
            "lang_re": re.compile(cfg["lang_regex"]) if cfg.get("lang_regex") else None,
        }
    return out


_MATCHERS = _build_matchers()


def parse_relative_time(text: Optional[str]) -> Optional[datetime]:
    """Parse YouTube relative time strings ("3 days ago", "Streamed 2 hours ago")
    into an approximate timezone-aware datetime.

    Returns None if the text cannot be parsed.
    """
    if not text:
        return None
    text_s = text.strip()
    # Strip leading prefixes like "Streamed ", "Premiered ", "Scheduled for "
    for prefix in ("Streamed ", "Premiered ", "Scheduled for "):
        if text_s.startswith(prefix):
            text_s = text_s[len(prefix):]
            break
    text_s = text_s.lower().replace("ago", "").strip()
    match = re.match(
        r"(\d+)\s*(minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)",
        text_s,
    )
    if not match:
        return None
    amount = int(match.group(1))
    unit = match.group(2)
    now = datetime.now(JST)
    if unit.startswith("minute"):
        return now - timedelta(minutes=amount)
    elif unit.startswith("hour"):
        return now - timedelta(hours=amount)
    elif unit.startswith("day"):
        return now - timedelta(days=amount)
    elif unit.startswith("week"):
        return now - timedelta(weeks=amount)
    elif unit.startswith("month"):
        return now - timedelta(days=amount * 30)
    elif unit.startswith("year"):
        return now - timedelta(days=amount * 365)
    return None


def parse_view_count(text: str) -> int:
    """Parse YouTube view count strings like "1.2M views", "500K views", "123 views"
    into an integer.  Returns 0 for unparseable input.
    """
    if not text:
        return 0
    text = text.replace("views", "").replace("view", "").strip().replace(",", "")
    if not text or text.lower() == "no":
        return 0
    multiplier = 1
    t = text.lower()
    if "k" in t:
        multiplier = 1_000
        t = t.replace("k", "")
    elif "m" in t:
        multiplier = 1_000_000
        t = t.replace("m", "")
    elif "b" in t:
        multiplier = 1_000_000_000
        t = t.replace("b", "")
    try:
        return int(float(t) * multiplier)
    except (ValueError, TypeError):
        return 0


def is_investment_related(title: str, region: str = DEFAULT_REGION) -> bool:
    """Check if a video title is genuinely investment / finance related.

    Strategy (region-driven):
      1. Reject if any shared NEGATIVE keyword is present (substring, ci).
      2. Accept if any region native-script term appears (substring — safe in CJK).
      3. Accept if any region Latin acronym/word appears as a *whole token*.

    Shared by the YouTube keyword scraper, Niconico, the official feed scraper
    and the channel deep-scraper so filtering stays consistent everywhere.
    """
    if not title:
        return False
    m = _MATCHERS.get(region) or _MATCHERS[DEFAULT_REGION]
    title_lower = title.lower()
    for kw in NEGATIVE_KEYWORDS:
        if kw.lower() in title_lower:
            return False
    for kw in m["native"]:
        if kw in title:
            return True
    if m["latin_ci_re"] and m["latin_ci_re"].search(title):
        return True
    if m["latin_cs_re"] and m["latin_cs_re"].search(title):
        return True
    return False


def is_native_lang(text: str, region: str = DEFAULT_REGION) -> bool:
    """True if *text* is written in the region's local script.

    Used by the scorer to give a small ranking bonus to local-language content
    (Japanese kana/kanji, Korean Hangul, English for Singapore).
    """
    if not text:
        return False
    m = _MATCHERS.get(region) or _MATCHERS[DEFAULT_REGION]
    return bool(m["lang_re"].search(text)) if m["lang_re"] else False
