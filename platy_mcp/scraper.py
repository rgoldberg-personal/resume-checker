"""Scraper for Platy.cz salary data."""
from __future__ import annotations

import json
import logging
import re
import time
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

BASE_URL = "https://www.platy.cz/platy/informacni-technologie"
_DATA_DIR = Path(__file__).parent / "data"

# Role slugs on platy.cz mapped to our canonical categories
ROLE_SLUG_MAP: dict[str, str] = {
    "programator": "software-engineer",
    "backend-developer": "backend-developer",
    "frontend-developer": "frontend-developer",
    "android-programator": "mobile-developer",
    "devops-specialista": "devops-engineer",
    "data-scientist": "data-scientist",
    "solution-architekt": "solutions-architect",
    "it-architekt": "it-architect",
    "ai-inzenyr": "ai-engineer",
    "specialista-it-bezpecnosti": "security-engineer",
    "it-tester": "qa-engineer",
    "produktovy-manazer-v-it": "product-manager",
    "ux-designer": "ux-designer",
    "cloud-specialista": "cloud-engineer",
    "systemovy-administrator": "system-admin",
    "it-projektovy-manazer": "project-manager",
    "databazovy-administrator": "database-admin",
    "scrum-master": "scrum-master",
}


def _parse_salary_number(text: str) -> int | None:
    """Parse a Czech salary number like '64 089' or '212 659' into an integer."""
    # Remove spaces and non-breaking spaces, keep digits
    cleaned = re.sub(r"[^\d]", "", text.strip())
    if cleaned:
        return int(cleaned)
    return None


def _extract_salary_data(html: str) -> dict | None:
    """Extract salary data from a Platy.cz role page HTML."""
    result: dict = {}

    # Pattern: "80% lidí vydělává: XXK - XXXK Kč" or the precise numbers
    # Look for the precise p10-p90 range: "XX XXX Kč" to "XXX XXX Kč"
    # Pattern for the two main salary figures (p10 and p90)
    salary_pattern = re.compile(
        r"(\d[\d\s]+)\s*Kč.*?(\d[\d\s]+)\s*Kč",
        re.DOTALL,
    )

    # Try to find the 80th percentile range
    p80_match = re.search(
        r"80\s*%.*?(\d[\d\s]+)\s*Kč.*?(\d[\d\s]+)\s*Kč",
        html,
        re.DOTALL | re.IGNORECASE,
    )
    if p80_match:
        p10 = _parse_salary_number(p80_match.group(1))
        p90 = _parse_salary_number(p80_match.group(2))
        if p10 and p90:
            result["p10_czk"] = p10
            result["p90_czk"] = p90

    # Try to find "after 5 years" salary
    exp_match = re.search(
        r"(?:po\s*5\s*let|after\s*5\s*year).*?(\d[\d\s]+)\s*Kč",
        html,
        re.IGNORECASE,
    )
    if exp_match:
        after_5 = _parse_salary_number(exp_match.group(1))
        if after_5:
            result["after_5_years_czk"] = after_5

    # Try to find sample size
    sample_match = re.search(
        r"(\d+)\s*(?:ověřených respondentů|verified respondent)",
        html,
        re.IGNORECASE,
    )
    if sample_match:
        result["sample_size"] = int(sample_match.group(1))
    else:
        # Look for "méně než 20" pattern
        if re.search(r"méně než\s*20|fewer than\s*20", html, re.IGNORECASE):
            result["sample_size"] = 20  # approximate

    return result if result.get("p10_czk") else None


def _interpolate_tiers(p10: int, p90: int) -> list[dict]:
    """
    Interpolate seniority tiers from the p10-p90 salary range.

    Platy.cz doesn't provide seniority breakdown, so we derive it:
    - junior: p10 to ~30th percentile
    - mid: ~30th to ~55th percentile
    - senior: ~55th to ~80th percentile
    - lead: ~80th percentile to p90+
    """
    spread = p90 - p10

    return [
        {
            "seniority_tier": "junior",
            "min_czk": p10,
            "max_czk": p10 + int(spread * 0.25),
        },
        {
            "seniority_tier": "mid",
            "min_czk": p10 + int(spread * 0.20),
            "max_czk": p10 + int(spread * 0.50),
        },
        {
            "seniority_tier": "senior",
            "min_czk": p10 + int(spread * 0.45),
            "max_czk": p10 + int(spread * 0.75),
        },
        {
            "seniority_tier": "lead",
            "min_czk": p10 + int(spread * 0.70),
            "max_czk": p90 + int(spread * 0.15),
        },
    ]


def scrape_role(slug: str, role_category: str, client: httpx.Client) -> list[dict] | None:
    """Scrape salary data for a single role from Platy.cz."""
    url = f"{BASE_URL}/{slug}"
    try:
        resp = client.get(url)
        if resp.status_code != 200:
            logger.warning("Failed to fetch %s: HTTP %d", url, resp.status_code)
            return None
    except httpx.HTTPError as e:
        logger.warning("HTTP error fetching %s: %s", url, e)
        return None

    data = _extract_salary_data(resp.text)
    if not data:
        logger.warning("No salary data extracted from %s", url)
        return None

    tiers = _interpolate_tiers(data["p10_czk"], data["p90_czk"])
    sample_size = data.get("sample_size", 0)

    entries = []
    for tier in tiers:
        entries.append({
            "role_category": role_category,
            "seniority_tier": tier["seniority_tier"],
            "min_czk": tier["min_czk"],
            "max_czk": tier["max_czk"],
            "source": "platy.cz",
            "source_url": url,
            "year": 2026,
            "sample_size": sample_size,
            "p10_czk": data["p10_czk"],
            "p90_czk": data["p90_czk"],
        })

    return entries


def scrape_all_roles(delay: float = 1.0) -> list[dict]:
    """Scrape all configured roles from Platy.cz with polite delays."""
    all_entries: list[dict] = []

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml",
        "Accept-Language": "cs,en;q=0.9",
    }

    with httpx.Client(headers=headers, follow_redirects=True, timeout=15.0) as client:
        for slug, role_category in ROLE_SLUG_MAP.items():
            logger.info("Scraping %s -> %s", slug, role_category)
            entries = scrape_role(slug, role_category, client)
            if entries:
                all_entries.extend(entries)
                logger.info("  Got %d tier entries (p10=%d, p90=%d)",
                           len(entries), entries[0]["p10_czk"], entries[0]["p90_czk"])
            else:
                logger.warning("  No data for %s", slug)

            time.sleep(delay)  # Be polite

    return all_entries


def save_scraped_data(entries: list[dict]) -> Path:
    """Save scraped data to salary_data.json."""
    output_path = _DATA_DIR / "salary_data.json"
    _DATA_DIR.mkdir(parents=True, exist_ok=True)

    with output_path.open("w") as f:
        json.dump(entries, f, indent=2, ensure_ascii=False)

    roles = sorted(set(e["role_category"] for e in entries))
    logger.info("Saved %d entries for %d roles to %s", len(entries), len(roles), output_path)
    return output_path


def refresh_salary_data(delay: float = 1.0) -> dict:
    """Full scrape + save pipeline. Returns summary stats."""
    entries = scrape_all_roles(delay=delay)
    if not entries:
        return {"status": "error", "message": "No data scraped", "entries": 0}

    save_scraped_data(entries)
    roles = set(e["role_category"] for e in entries)
    return {
        "status": "ok",
        "entries": len(entries),
        "roles_count": len(roles),
        "roles": sorted(roles),
    }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = refresh_salary_data()
    print(json.dumps(result, indent=2))
