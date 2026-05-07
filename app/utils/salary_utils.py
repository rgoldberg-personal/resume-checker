"""Salary estimation support utilities."""
from __future__ import annotations

import logging
import re
from pathlib import Path

import httpx
import yaml

logger = logging.getLogger(__name__)

_CONFIG_DIR = Path(__file__).parent.parent.parent / "config"

_SALARY_BANDS_CACHE: dict | None = None

# Plausibility bounds for CZK monthly salary
_MIN_PLAUSIBLE = 25_000
_MAX_PLAUSIBLE = 500_000


def _load_salary_bands() -> dict:
    global _SALARY_BANDS_CACHE
    if _SALARY_BANDS_CACHE is None:
        with (_CONFIG_DIR / "salary_bands.yaml").open() as f:
            _SALARY_BANDS_CACHE = yaml.safe_load(f)
    return _SALARY_BANDS_CACHE



def score_to_seniority_tier(total_score: int) -> str:
    """
    Convert a 0-100 seniority score to a seniority tier label.

    Bands:
        0-34   → junior
        35-59  → mid
        60-79  → senior
        80-100 → lead
    """
    if total_score < 35:
        return "junior"
    if total_score < 60:
        return "mid"
    if total_score < 80:
        return "senior"
    return "lead"


def fallback_salary_bands(role_category: str, seniority_tier: str) -> dict:
    """
    Return fallback salary band data from config/salary_bands.yaml.

    Falls back to 'software-engineer' if the role category is not found,
    and to 'mid' tier if the seniority tier is not found.
    Returns dict with: min_czk, max_czk, data_source.
    """
    bands = _load_salary_bands().get("bands", {})

    role_bands = bands.get(role_category) or bands.get("software-engineer", {})
    tier_data = role_bands.get(seniority_tier) or role_bands.get("mid") or {}

    return {
        "min_czk": tier_data.get("min_czk", 40_000),
        "max_czk": tier_data.get("max_czk", 70_000),
        "data_source": "fallback_bands",
    }


# Platy.cz slug mapping for live scraping
_ROLE_TO_PLATY_SLUG: dict[str, str] = {
    "software-engineer": "programator",
    "backend-developer": "backend-developer",
    "frontend-developer": "frontend-developer",
    "mobile-developer": "android-programator",
    "devops-engineer": "devops-specialista",
    "data-scientist": "data-scientist",
    "solutions-architect": "solution-architekt",
    "it-architect": "it-architekt",
    "ai-engineer": "ai-inzenyr",
    "security-engineer": "specialista-it-bezpecnosti",
    "qa-engineer": "it-tester",
    "product-manager": "produktovy-manazer-v-it",
    "ux-designer": "ux-designer",
    "cloud-engineer": "cloud-specialista",
    "system-admin": "systemovy-administrator",
    "project-manager": "it-projektovy-manazer",
    "database-admin": "databazovy-administrator",
    "scrum-master": "scrum-master",
}

_PLATY_BASE_URL = "https://www.platy.cz/platy/informacni-technologie"


def _parse_salary_number(text: str) -> int | None:
    """Parse Czech salary number like '64 089' into int."""
    cleaned = re.sub(r"[^\d]", "", text.strip())
    return int(cleaned) if cleaned else None


def _interpolate_tier(p10: int, p90: int, seniority_tier: str) -> dict:
    """Interpolate a specific tier from the p10-p90 range."""
    spread = p90 - p10
    tiers = {
        "junior": (0.0, 0.25),
        "mid": (0.20, 0.50),
        "senior": (0.45, 0.75),
        "lead": (0.70, 1.15),
    }
    low_pct, high_pct = tiers.get(seniority_tier, (0.45, 0.75))
    return {
        "min_czk": p10 + int(spread * low_pct),
        "max_czk": p10 + int(spread * high_pct),
    }


def fetch_live_salary(role_category: str, seniority_tier: str) -> dict | None:
    """
    Scrape live salary data from Platy.cz for a specific role and tier.

    Returns dict with min_czk, max_czk, data_source, p10_czk, p90_czk
    or None if scraping fails.
    """
    slug = _ROLE_TO_PLATY_SLUG.get(role_category)
    if not slug:
        logger.warning("No Platy.cz slug for role: %s", role_category)
        return None

    url = f"{_PLATY_BASE_URL}/{slug}"
    try:
        resp = httpx.get(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
                "Accept-Language": "cs,en;q=0.9",
            },
            follow_redirects=True,
            timeout=10.0,
        )
        if resp.status_code != 200:
            logger.warning("Platy.cz returned %d for %s", resp.status_code, url)
            return None
    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        return None

    # Extract p10-p90 range from HTML
    match = re.search(
        r"80\s*%.*?(\d[\d\s]+)\s*Kč.*?(\d[\d\s]+)\s*Kč",
        resp.text,
        re.DOTALL | re.IGNORECASE,
    )
    if not match:
        logger.warning("Could not parse salary data from %s", url)
        return None

    p10 = _parse_salary_number(match.group(1))
    p90 = _parse_salary_number(match.group(2))
    if not p10 or not p90:
        return None

    tier_range = _interpolate_tier(p10, p90, seniority_tier)
    return {
        "min_czk": tier_range["min_czk"],
        "max_czk": tier_range["max_czk"],
        "data_source": "platy_cz_live",
        "source_url": url,
        "p10_czk": p10,
        "p90_czk": p90,
    }


def validate_salary_sanity(min_czk: int, max_czk: int) -> bool:
    """
    Return True if both min and max are within plausible CZK monthly salary bounds.

    Plausible range: 25,000 – 500,000 CZK/month.
    """
    return (
        _MIN_PLAUSIBLE <= min_czk <= _MAX_PLAUSIBLE
        and _MIN_PLAUSIBLE <= max_czk <= _MAX_PLAUSIBLE
    )
