"""Integration tests for Platy MCP server tools (direct import — no subprocess)."""
from __future__ import annotations

from platy_mcp.tools import get_market_stats, get_salary_range, list_roles


def test_get_salary_range_software_engineer_senior() -> None:
    result = get_salary_range("software-engineer", "senior")
    assert result["min_czk"] > 0
    assert result["max_czk"] > result["min_czk"]
    assert result["found"] is True
    assert result["min_czk"] == 90000
    assert result["max_czk"] == 140000


def test_get_salary_range_exact_match_returns_correct_data() -> None:
    result = get_salary_range("devops-engineer", "mid")
    assert result["found"] is True
    assert result["role_category"] == "devops-engineer"
    assert result["seniority_tier"] == "mid"
    assert result["min_czk"] > 0
    assert result["max_czk"] > result["min_czk"]
    assert result["source"] == "platy.cz"
    assert result["year"] == 2025


def test_get_salary_range_unknown_role_returns_fallback() -> None:
    result = get_salary_range("unknown-role-xyz", "mid")
    assert result["min_czk"] > 0  # returns software-engineer/mid fallback
    assert result["max_czk"] > result["min_czk"]
    assert result["found"] is False


def test_get_salary_range_unknown_tier_falls_back_to_same_role() -> None:
    result = get_salary_range("frontend-developer", "principal")
    # No 'principal' tier exists — should return a frontend-developer entry
    assert result["role_category"] == "frontend-developer"
    assert result["found"] is False
    assert result["min_czk"] > 0


def test_list_roles_returns_all_13_categories() -> None:
    roles = list_roles()
    assert isinstance(roles, list)
    assert len(roles) == 13
    expected = [
        "software-engineer",
        "frontend-developer",
        "backend-developer",
        "fullstack-developer",
        "data-scientist",
        "data-engineer",
        "devops-engineer",
        "qa-engineer",
        "product-manager",
        "ux-designer",
        "mobile-developer",
        "security-engineer",
        "solutions-architect",
    ]
    for role in expected:
        assert role in roles, f"Expected role '{role}' not found in list_roles()"


def test_list_roles_contains_software_engineer() -> None:
    roles = list_roles()
    assert "software-engineer" in roles
    assert len(roles) >= 5


def test_get_market_stats_returns_all_tiers() -> None:
    stats = get_market_stats("software-engineer")
    assert "tiers" in stats
    assert stats["role_category"] == "software-engineer"
    assert len(stats["tiers"]) >= 3

    tier_names = {t["tier"] for t in stats["tiers"]}
    assert "junior" in tier_names
    assert "mid" in tier_names
    assert "senior" in tier_names

    for tier in stats["tiers"]:
        assert tier["min_czk"] > 0
        assert tier["max_czk"] > tier["min_czk"]
        assert tier["median_czk"] == (tier["min_czk"] + tier["max_czk"]) // 2


def test_get_market_stats_year_field() -> None:
    stats = get_market_stats("data-scientist")
    assert stats["year"] == 2025


def test_get_market_stats_unknown_role_returns_empty_tiers() -> None:
    stats = get_market_stats("nonexistent-role")
    assert stats["role_category"] == "nonexistent-role"
    assert stats["tiers"] == []


def test_all_roles_have_salary_data() -> None:
    """Every role returned by list_roles() must have at least one salary entry."""
    roles = list_roles()
    for role in roles:
        stats = get_market_stats(role)
        assert len(stats["tiers"]) > 0, f"No salary data for role '{role}'"


def test_all_roles_have_four_tiers() -> None:
    """Every canonical role must have all 4 seniority tiers covered."""
    roles = list_roles()
    expected_tiers = {"junior", "mid", "senior", "lead"}
    for role in roles:
        stats = get_market_stats(role)
        tier_names = {t["tier"] for t in stats["tiers"]}
        assert expected_tiers == tier_names, (
            f"Role '{role}' missing tiers: {expected_tiers - tier_names}"
        )


def test_salary_ranges_within_realistic_bounds() -> None:
    """All salary entries should be within plausible CZK/month bounds."""
    roles = list_roles()
    for role in roles:
        result_junior = get_salary_range(role, "junior")
        result_lead = get_salary_range(role, "lead")
        assert result_junior["found"] is True
        assert result_lead["found"] is True
        # Junior must be within 25k–100k
        assert result_junior["min_czk"] >= 25000
        assert result_junior["max_czk"] <= 100000
        # Lead must be within 100k–250k
        assert result_lead["min_czk"] >= 100000
        assert result_lead["max_czk"] <= 250000
