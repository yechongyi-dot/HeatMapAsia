"""Single source of truth for the app version and its GitHub home.

The in-app updater (web/update.py) compares __version__ against the latest
GitHub Release tag of GITHUB_OWNER/GITHUB_REPO. Bump __version__ here, then run
`python scripts/release.py` to build and publish a matching release.
"""

__version__ = "0.1.1"

# GitHub repository that hosts releases for the in-app updater.
# (Create this repo before the first `python scripts/release.py`; until then the
# updater simply finds no release and stays quiet.)
GITHUB_OWNER = "yechongyi-dot"
GITHUB_REPO = "HeatMapAsia"


def repo_slug() -> str:
    """``owner/repo`` string used to build GitHub API URLs."""
    return f"{GITHUB_OWNER}/{GITHUB_REPO}"
