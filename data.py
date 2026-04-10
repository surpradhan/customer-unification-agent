"""
Shared data loading and schema validation for the Customer Unification Agent.

All file I/O should go through this module so validation and unique_id
generation happen in one place.
"""

import logging

import pandas as pd

from config import (
    AUTO_MERGE_CSV,
    GROUND_TRUTH_CSV,
    GROUND_TRUTH_HARD_CSV,
    SHOPIFY_CSV,
    SHOPIFY_HARD_CSV,
    STRIPE_CSV,
    STRIPE_HARD_CSV,
)

logger = logging.getLogger(__name__)

# Required columns for each dataset
_SHOPIFY_REQUIRED: set[str] = {"name", "email", "phone", "address", "zipcode", "true_customer_id"}
_STRIPE_REQUIRED: set[str] = {"name", "email", "phone", "address", "zipcode", "true_customer_id"}
_MATCHES_REQUIRED: set[str] = {
    "unique_id_l", "unique_id_r", "match_probability", "name_l", "email_l",
}


def _validate_columns(df: pd.DataFrame, required: set[str], label: str) -> None:
    """Raise ValueError if any required columns are missing from df."""
    missing = required - set(df.columns)
    if missing:
        raise ValueError(f"{label} is missing required columns: {sorted(missing)}")


def add_unique_ids(
    shopify_df: pd.DataFrame, stripe_df: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Add platform-prefixed unique_id columns if not already present.

    Returns:
        (shopify_df, stripe_df) copies with unique_id added.
    """
    shopify_df = shopify_df.copy()
    stripe_df = stripe_df.copy()

    if "unique_id" not in shopify_df.columns:
        shopify_df["unique_id"] = "SHOPIFY_" + shopify_df.index.astype(str)
    if "unique_id" not in stripe_df.columns:
        stripe_df["unique_id"] = "STRIPE_" + stripe_df.index.astype(str)

    return shopify_df, stripe_df


def load_raw_data(use_hard_cases: bool = False) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    Load Shopify and Stripe CSVs, validate schema, and add unique_ids.

    Args:
        use_hard_cases: Load the hard-cases variants when True.

    Returns:
        (shopify_df, stripe_df)

    Raises:
        FileNotFoundError: If a CSV file does not exist.
        ValueError: If required columns are missing.
    """
    shopify_path = SHOPIFY_HARD_CSV if use_hard_cases else SHOPIFY_CSV
    stripe_path = STRIPE_HARD_CSV if use_hard_cases else STRIPE_CSV

    shopify_df = pd.read_csv(shopify_path)
    stripe_df = pd.read_csv(stripe_path)

    _validate_columns(shopify_df, _SHOPIFY_REQUIRED, shopify_path)
    _validate_columns(stripe_df, _STRIPE_REQUIRED, stripe_path)

    shopify_df, stripe_df = add_unique_ids(shopify_df, stripe_df)

    logger.info("Loaded %d Shopify records from %s", len(shopify_df), shopify_path)
    logger.info("Loaded %d Stripe records from %s", len(stripe_df), stripe_path)

    return shopify_df, stripe_df


def load_matches(csv_path: str = AUTO_MERGE_CSV) -> pd.DataFrame:
    """
    Load a matches CSV and validate required columns.

    Args:
        csv_path: Path to the matches CSV file.

    Raises:
        FileNotFoundError: If the file does not exist.
        ValueError: If required columns are missing.
    """
    matches_df = pd.read_csv(csv_path)
    _validate_columns(matches_df, _MATCHES_REQUIRED, csv_path)
    logger.info("Loaded %d matches from %s", len(matches_df), csv_path)
    return matches_df


def load_ground_truth(use_hard_cases: bool = False) -> pd.DataFrame:
    """
    Load the ground truth CSV.

    Args:
        use_hard_cases: Load the hard-cases variant when True.
    """
    path = GROUND_TRUTH_HARD_CSV if use_hard_cases else GROUND_TRUTH_CSV
    df = pd.read_csv(path)
    logger.info("Loaded %d ground truth records from %s", len(df), path)
    return df


def load_dashboard_data() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """
    Convenience loader for the dashboard.

    Loads hard-cases variants of Shopify, Stripe, auto-merge matches, and ground truth.

    Returns:
        (shopify_df, stripe_df, matches_df, ground_truth_df)
    """
    shopify_df, stripe_df = load_raw_data(use_hard_cases=True)
    matches_df = load_matches(AUTO_MERGE_CSV)
    ground_truth_df = load_ground_truth(use_hard_cases=True)
    return shopify_df, stripe_df, matches_df, ground_truth_df
