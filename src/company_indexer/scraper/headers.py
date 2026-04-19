"""User-agent rotation and full matching header sets.

Each entry is a realistic current-stable browser profile: UA string plus the
other headers that browser sends on a top-level navigation to an HTTPS site.
Picked deterministically per scrape (hash of company id) so behavior is
reproducible when debugging why a given domain blocked us.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class BrowserProfile:
    user_agent: str
    sec_ch_ua: str
    sec_ch_ua_platform: str


_PROFILES: tuple[BrowserProfile, ...] = (
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"macOS"',
    ),
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/131.0.0.0 Safari/537.36"
        ),
        sec_ch_ua='"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        sec_ch_ua_platform='"Windows"',
    ),
    BrowserProfile(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) "
            "Gecko/20100101 Firefox/133.0"
        ),
        sec_ch_ua="",
        sec_ch_ua_platform="",
    ),
)


def pick_profile(seed: int) -> BrowserProfile:
    return _PROFILES[seed % len(_PROFILES)]


def build_headers(profile: BrowserProfile) -> dict[str, str]:
    headers = {
        "User-Agent": profile.user_agent,
        "Accept": (
            "text/html,application/xhtml+xml,application/xml;q=0.9,"
            "image/avif,image/webp,*/*;q=0.8"
        ),
        "Accept-Language": "nl-NL,nl;q=0.9,en;q=0.8",
        "Accept-Encoding": "gzip, deflate, br",
        "Upgrade-Insecure-Requests": "1",
        "DNT": "1",
        "Connection": "keep-alive",
    }
    if profile.sec_ch_ua:
        headers["sec-ch-ua"] = profile.sec_ch_ua
        headers["sec-ch-ua-mobile"] = "?0"
        headers["sec-ch-ua-platform"] = profile.sec_ch_ua_platform
        headers["Sec-Fetch-Dest"] = "document"
        headers["Sec-Fetch-Mode"] = "navigate"
        headers["Sec-Fetch-Site"] = "none"
        headers["Sec-Fetch-User"] = "?1"
    return headers
