"""Cross-region scraper tuning (rate limits, windows, worker counts).

Region-specific data (search keywords, official channels, title-filter
vocabulary, language detection) lives in :mod:`scraper.regions`.
"""

# Time windows: label -> max age in hours.
# 30d mainly serves the sparse sources (official gov channels, niconico) whose
# content is too infrequent to show up in the shorter windows.
TIME_WINDOWS = {
    "24h": 24,
    "3d": 72,
    "7d": 168,
    "30d": 720,
}

# Max results per keyword per platform
RESULTS_PER_KEYWORD = 50

# Final top-N per platform per window
TOP_N = 300

# Delay between keyword searches (seconds), used within batches.
# YouTube uses the unofficial InnerTube API → keep polite to avoid soft-bans.
REQUEST_DELAY = 1.0
REQUEST_JITTER = 1.5

# Niconico uses the official Snapshot Search API → much higher tolerance,
# so it can run with a shorter delay and more workers.
NICONICO_DELAY = 0.3
NICONICO_JITTER = 0.4

# Concurrent workers per platform (keyword-level parallelism)
YOUTUBE_WORKERS = 5
NICONICO_WORKERS = 5

# Parallel channel-feed fetchers for the official scraper.
OFFICIAL_WORKERS = 5
