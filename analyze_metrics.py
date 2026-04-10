"""
CLI preview of dashboard metrics — uses shared data and metrics modules.

Usage:
    python analyze_metrics.py               # uses base dataset (matches matching_engine.py default)
    python analyze_metrics.py --hard-cases  # uses *_with_hard_cases.csv variants
"""

import argparse
import logging

from data import load_raw_data, load_matches
from metrics import calculate_summary_metrics, top_customers
from config import AUTO_MERGE_CSV

logger = logging.getLogger(__name__)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Preview dashboard metrics from saved match results."
    )
    parser.add_argument(
        "--hard-cases",
        action="store_true",
        help="Load the hard-cases dataset variants (*_with_hard_cases.csv).",
    )
    args = parser.parse_args()

    shopify_df, stripe_df = load_raw_data(use_hard_cases=args.hard_cases)
    matches_df = load_matches(AUTO_MERGE_CSV)

    summary = calculate_summary_metrics(shopify_df, stripe_df, matches_df)

    print("=" * 60)
    print("DASHBOARD METRICS PREVIEW")
    print("=" * 60)

    print(f"\nSummary:")
    print(f"  Total records:    {summary['total_records']}")
    print(f"  Duplicates found: {summary['duplicates_found']}")
    print(f"  Unique customers: {summary['unique_customers']}")
    reduction = summary["duplicates_found"] / summary["total_records"] * 100
    print(f"  Reduction:        {reduction:.1f}%")

    print(f"\nHidden Value:")
    print(f"  Total combined value: ${summary['hidden_value']:,.2f}")
    if summary["duplicates_found"] > 0:
        avg = summary["hidden_value"] / summary["duplicates_found"]
        print(f"  Average per customer: ${avg:,.2f}")

    cp = summary["cross_platform_customers"]
    if not cp.empty:
        print(f"\nTop 5 Cross-Platform Customers:")
        for i, (_, row) in enumerate(top_customers(cp, n=5).iterrows(), start=1):
            print(
                f"  {i}. {row['name']}: ${row['total_value']:,.2f}"
                f"  (Shopify: ${row['shopify_spent']:,.2f},"
                f"  Stripe: ${row['stripe_value']:,.2f})"
            )

    print("\n" + "=" * 60)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    main()
