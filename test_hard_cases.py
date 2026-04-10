"""
Run matching engine on data with hard cases
"""

import logging

import pandas as pd

from config import AUTO_MERGE_THRESHOLD, REVIEW_THRESHOLD
from data import load_raw_data
from matching_engine import CustomerMatcher

logger = logging.getLogger(__name__)


def main():
    """Run matching on dataset with hard cases."""
    logger.info("Loading data with hard cases...")
    shopify_df, stripe_df = load_raw_data(use_hard_cases=True)

    matcher = CustomerMatcher(
        auto_merge_threshold=AUTO_MERGE_THRESHOLD,
        review_threshold=REVIEW_THRESHOLD,
    )
    
    # Run pipeline
    pipeline_results = matcher.run_full_pipeline(shopify_df, stripe_df)
    
    logger.info("Sample auto-merge matches:")
    for _, row in pipeline_results["results"]["auto_merge"].head(3).iterrows():
        logger.info(
            "  prob=%.3f  left='%s | %s'  right='%s | %s'",
            row["match_probability"],
            row["name_l"], row["email_l"],
            row["name_r"], row["email_r"],
        )

    logger.info("=" * 60)
    logger.info("ANALYZING HARD CASES")
    logger.info("=" * 60)

    matches_df = pipeline_results["matches_df"]
    combined_df = pipeline_results["combined_df"]

    hard_case_ids = combined_df[
        combined_df["true_customer_id"].str.contains("CUST_HARD", na=False)
    ]["unique_id"].tolist()

    hard_case_matches = matches_df[
        matches_df["unique_id_l"].isin(hard_case_ids) |
        matches_df["unique_id_r"].isin(hard_case_ids)
    ]

    hard_auto_merge = hard_case_matches[
        hard_case_matches["match_probability"] >= AUTO_MERGE_THRESHOLD
    ]
    hard_review = hard_case_matches[
        (hard_case_matches["match_probability"] >= REVIEW_THRESHOLD) &
        (hard_case_matches["match_probability"] < AUTO_MERGE_THRESHOLD)
    ]
    hard_missed = len(hard_case_ids) // 2 - len(hard_case_matches)

    logger.info("Hard case matches found: %d", len(hard_case_matches))
    logger.info("Hard case breakdown:")
    logger.info("  Auto-merged:    %d", len(hard_auto_merge))
    logger.info("  Review queue:   %d", len(hard_review))
    logger.info("  Missed entirely: %d", hard_missed)

    for label, subset in [("auto-merged", hard_auto_merge), ("review queue", hard_review)]:
        if not subset.empty:
            logger.info("Sample hard cases in %s:", label)
            for _, row in subset.head(3).iterrows():
                logger.info(
                    "  prob=%.3f  left='%s | %s | %s'  right='%s | %s | %s'",
                    row["match_probability"],
                    row["name_l"], row["email_l"], row["phone_l"],
                    row["name_r"], row["email_r"], row["phone_r"],
                )

    if hard_missed > 0:
        logger.warning("%d hard cases were MISSED (did not pass blocking rules)", hard_missed)

    return pipeline_results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    results = main()
