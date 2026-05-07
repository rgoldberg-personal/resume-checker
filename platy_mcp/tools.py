"""MCP tool definitions for the Platy salary data server."""
from __future__ import annotations

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from platy_mcp.scraper import refresh_salary_data

mcp = FastMCP("platy-salary-mcp")

_DATA_DIR = Path(__file__).parent / "data"


def _load_salary_data() -> list[dict]:
    path = _DATA_DIR / "salary_data.json"
    with path.open() as f:
        return json.load(f)


@mcp.tool()
def get_salary_range(role_category: str, seniority_tier: str) -> dict:
    """
    Returns salary range for a given role and seniority tier from Platy.cz data.

    Args:
        role_category: One of the canonical role categories (see list_roles tool).
                       Use 'software-engineer' as default for unknown IT roles.
        seniority_tier: One of 'junior', 'mid', 'senior', 'lead', 'principal'

    Returns:
        {
            "role_category": str,
            "seniority_tier": str,
            "min_czk": int,
            "max_czk": int,
            "source": "platy.cz",
            "year": int,
            "sample_size": int,
            "found": bool  # false if no exact match, returns closest
        }
    """
    data = _load_salary_data()

    # Exact match first
    for entry in data:
        if entry["role_category"] == role_category and entry["seniority_tier"] == seniority_tier:
            return {**entry, "found": True}

    # Fallback: same role, any seniority
    for entry in data:
        if entry["role_category"] == role_category:
            return {**entry, "found": False}

    # Fallback: software-engineer / mid as default
    for entry in data:
        if entry["role_category"] == "software-engineer" and entry["seniority_tier"] == "mid":
            return {**entry, "found": False}

    # Last resort: first entry
    if data:
        return {**data[0], "found": False}

    raise ValueError("No salary data available")


@mcp.tool()
def list_roles() -> list[str]:
    """
    Returns all canonical role category strings supported by the salary database.
    Use this to find the correct role_category string before calling get_salary_range.
    """
    data = _load_salary_data()
    return sorted(set(entry["role_category"] for entry in data))


@mcp.tool()
def refresh_data() -> dict:
    """
    Re-scrape all salary data from Platy.cz and update the local cache.
    This fetches live data from ~20 IT role pages with 1s delay between requests.
    Takes approximately 20-30 seconds to complete.

    Returns:
        {
            "status": "ok" | "error",
            "entries": int,
            "roles_count": int,
            "roles": list[str]
        }
    """
    return refresh_salary_data(delay=1.0)


@mcp.tool()
def get_market_stats(role_category: str) -> dict:
    """
    Returns market statistics across all seniority tiers for a role.

    Returns:
        {
            "role_category": str,
            "tiers": [
                {
                    "tier": str,
                    "median_czk": int,
                    "min_czk": int,
                    "max_czk": int
                }
            ],
            "year": int
        }
    """
    data = _load_salary_data()
    tiers = []
    year = 2025

    for entry in data:
        if entry["role_category"] == role_category:
            median = (entry["min_czk"] + entry["max_czk"]) // 2
            tiers.append(
                {
                    "tier": entry["seniority_tier"],
                    "median_czk": median,
                    "min_czk": entry["min_czk"],
                    "max_czk": entry["max_czk"],
                }
            )
            year = entry.get("year", year)

    return {
        "role_category": role_category,
        "tiers": tiers,
        "year": year,
    }
