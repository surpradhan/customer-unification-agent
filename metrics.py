"""
Shared metrics calculations for the Customer Unification Agent.

Used by both dashboard.py and analyze_metrics.py so the logic lives in
one place and both consumers stay in sync.
"""

import logging

import pandas as pd

from config import VIP_SPEND_THRESHOLD

logger = logging.getLogger(__name__)


def calculate_cross_platform_value(
    shopify_df: pd.DataFrame,
    stripe_df: pd.DataFrame,
    matches_df: pd.DataFrame,
) -> tuple[float, pd.DataFrame]:
    """
    Compute combined Shopify + Stripe value for each matched pair using vectorized merges.

    Args:
        shopify_df: Shopify records with unique_id and total_spent.
        stripe_df:  Stripe records with unique_id and lifetime_value.
        matches_df: Match results with unique_id_l, unique_id_r, name_l, email_l,
                    match_probability.

    Returns:
        (total_hidden_value, cross_platform_df) where cross_platform_df has columns:
        shopify_uid, stripe_uid, name, email, match_confidence,
        shopify_spent, stripe_value, total_value.
    """
    matches = matches_df.copy()

    # Determine which side is Shopify vs Stripe via vectorized string check
    shopify_is_left = matches["unique_id_l"].str.contains("SHOPIFY", na=False)
    matches["shopify_uid"] = matches["unique_id_l"].where(shopify_is_left, matches["unique_id_r"])
    matches["stripe_uid"] = matches["unique_id_r"].where(shopify_is_left, matches["unique_id_l"])
    matches["name"] = matches["name_l"]
    matches["email"] = matches["email_l"]
    matches["match_confidence"] = matches["match_probability"]

    # Build lookup tables for the two value columns
    shopify_lookup = (
        shopify_df[["unique_id", "total_spent"]]
        .rename(columns={"unique_id": "shopify_uid", "total_spent": "shopify_spent"})
    )
    stripe_lookup = (
        stripe_df[["unique_id", "lifetime_value"]]
        .rename(columns={"unique_id": "stripe_uid", "lifetime_value": "stripe_value"})
    )

    result = (
        matches[["shopify_uid", "stripe_uid", "name", "email", "match_confidence"]]
        .merge(shopify_lookup, on="shopify_uid", how="left")
        .merge(stripe_lookup, on="stripe_uid", how="left")
    )

    result["shopify_spent"] = result["shopify_spent"].fillna(0)
    result["stripe_value"] = result["stripe_value"].fillna(0)
    result["total_value"] = result["shopify_spent"] + result["stripe_value"]

    # Drop rows where neither side resolved to a real record
    result = result[(result["shopify_spent"] > 0) | (result["stripe_value"] > 0)]

    hidden_value: float = float(result["total_value"].sum())
    logger.info(
        "Calculated combined value: $%.2f across %d matched pairs",
        hidden_value,
        len(result),
    )

    return hidden_value, result


def calculate_summary_metrics(
    shopify_df: pd.DataFrame,
    stripe_df: pd.DataFrame,
    matches_df: pd.DataFrame,
    precision: float | None = None,
) -> dict:
    """
    Calculate top-level business KPIs.

    Args:
        shopify_df:  Shopify records (must have unique_id, total_spent).
        stripe_df:   Stripe records (must have unique_id, lifetime_value).
        matches_df:  Auto-merge match results.
        precision:   Validation precision from matching_engine; None if not yet computed.

    Returns:
        Dict with keys: total_records, duplicates_found, unique_customers,
        hidden_value, cross_platform_customers (DataFrame), precision.
    """
    total_records = len(shopify_df) + len(stripe_df)
    duplicates_found = len(matches_df)
    unique_customers = total_records - duplicates_found

    hidden_value, cross_platform_df = calculate_cross_platform_value(
        shopify_df, stripe_df, matches_df
    )

    return {
        "total_records": total_records,
        "duplicates_found": duplicates_found,
        "unique_customers": unique_customers,
        "hidden_value": hidden_value,
        "cross_platform_customers": cross_platform_df,
        "precision": precision,
    }


def top_customers(cross_platform_df: pd.DataFrame, n: int = 10) -> pd.DataFrame:
    """Return the top-n cross-platform customers by total_value."""
    return cross_platform_df.nlargest(n, "total_value")


def vip_count(cross_platform_df: pd.DataFrame) -> int:
    """Number of customers whose total_value exceeds VIP_SPEND_THRESHOLD."""
    return int((cross_platform_df["total_value"] > VIP_SPEND_THRESHOLD).sum())
