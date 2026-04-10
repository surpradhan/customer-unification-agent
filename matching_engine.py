"""
Customer Record Matching Engine using Splink
Implements probabilistic record linkage with configurable thresholds
"""

import json
import logging
import os

import pandas as pd
from splink import DuckDBAPI, Linker, SettingsCreator, block_on
import splink.comparison_library as cl

from config import AUTO_MERGE_CSV, AUTO_MERGE_THRESHOLD, REVIEW_QUEUE_CSV, REVIEW_THRESHOLD, VALIDATION_METRICS_JSON

logger = logging.getLogger(__name__)


class CustomerMatcher:
    """
    Matches customer records across platforms using probabilistic record linkage.
    """

    def __init__(self, auto_merge_threshold: float = 0.95, review_threshold: float = 0.75) -> None:
        """
        Initialize matcher with confidence thresholds.

        Args:
            auto_merge_threshold: Confidence above which records auto-merge (default: 0.95)
            review_threshold: Confidence above which records flagged for review (default: 0.75)
        """
        self.auto_merge_threshold = auto_merge_threshold
        self.review_threshold = review_threshold
        self.linker = None

    def prepare_data(
        self, shopify_df: pd.DataFrame, stripe_df: pd.DataFrame
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Validate and prepare each platform's records for linking.

        Returns the two DataFrames separately (not combined) so the linker can
        use ``link_type="link_only"`` and never generate same-platform candidate
        pairs.

        Args:
            shopify_df: Raw Shopify customer records.
            stripe_df:  Raw Stripe customer records.

        Returns:
            (shopify_prepped, stripe_prepped) — each with a unique_id column added.

        Raises:
            ValueError: If either DataFrame is empty or missing required columns.
        """
        if shopify_df.empty:
            raise ValueError("shopify_df is empty — cannot run matching pipeline.")
        if stripe_df.empty:
            raise ValueError("stripe_df is empty — cannot run matching pipeline.")

        required = {"name", "email", "phone", "address", "zipcode", "true_customer_id"}
        for label, df in [("shopify_df", shopify_df), ("stripe_df", stripe_df)]:
            missing = required - set(df.columns)
            if missing:
                raise ValueError(f"{label} is missing columns: {sorted(missing)}")

        shopify_df = shopify_df.copy()
        stripe_df = stripe_df.copy()

        shopify_df["unique_id"] = "SHOPIFY_" + shopify_df.index.astype(str)
        stripe_df["unique_id"] = "STRIPE_" + stripe_df.index.astype(str)

        cols = [
            "unique_id", "source_platform", "source_customer_id",
            "name", "email", "phone", "address", "zipcode", "true_customer_id",
        ]

        shopify_prepped = shopify_df[cols]
        stripe_prepped = stripe_df[cols]

        logger.info("Prepared data for matching:")
        logger.info("  Shopify: %d records", len(shopify_prepped))
        logger.info("  Stripe:  %d records", len(stripe_prepped))

        return shopify_prepped, stripe_prepped

    def configure_splink(self) -> SettingsCreator:
        """
        Configure Splink settings for matching.

        Uses ``link_type="link_only"`` so Splink only generates candidate pairs
        across the two platforms, never within the same platform.

        Returns:
            SettingsCreator object with Splink v4 configuration.
        """
        settings = SettingsCreator(
            link_type="link_only",
            unique_id_column_name="unique_id",
            blocking_rules_to_generate_predictions=[
                # Block on exact email match
                block_on("email"),
                # Block on first 6 characters of email (catches alias/typo variants)
                "substr(l.email, 1, 6) = substr(r.email, 1, 6)",
                # Block on exact phone (after removing formatting)
                block_on("phone"),
                # Block on exact zipcode
                block_on("zipcode"),
            ],
            comparisons=[
                # Email — most reliable signal; Levenshtein catches typos/aliases
                cl.LevenshteinAtThresholds("email", [1, 2]).configure(
                    term_frequency_adjustments=True
                ),
                # Name — Jaro-Winkler handles initials, reversed tokens, abbreviations
                cl.JaroWinklerAtThresholds("name", [0.9, 0.8]),
                # Phone — formatting varies widely between platforms
                cl.LevenshteinAtThresholds("phone", [2, 5]),
                # Address — abbreviations (St/Street, Apt/Suite) are common
                cl.LevenshteinAtThresholds("address", [5, 10]),
                # Zipcode — exact match is a strong anchor signal
                cl.ExactMatch("zipcode"),
            ],
            retain_matching_columns=True,
            retain_intermediate_calculation_columns=True,
        )

        return settings

    def train_model(self, shopify_df: pd.DataFrame, stripe_df: pd.DataFrame) -> None:
        """
        Train the Splink model.

        Args:
            shopify_df: Prepared Shopify records (with unique_id).
            stripe_df:  Prepared Stripe records (with unique_id).

        Raises:
            ValueError: If either DataFrame is empty.
            RuntimeError: If Splink initialisation or training fails.
        """
        if shopify_df.empty or stripe_df.empty:
            raise ValueError("Cannot train model: one or both DataFrames are empty.")

        logger.info("Configuring Splink...")
        settings = self.configure_splink()

        logger.info("Initializing linker (link_only mode: Shopify × Stripe only)...")
        try:
            # Two separate DataFrames → link_only generates only cross-platform pairs
            self.linker = Linker([shopify_df, stripe_df], settings, db_api=DuckDBAPI())
        except Exception as exc:
            raise RuntimeError(f"Failed to initialize Splink linker: {exc}") from exc

        logger.info("Estimating u-probabilities via random sampling...")
        try:
            self.linker.training.estimate_u_using_random_sampling(max_pairs=1e6)
        except Exception as exc:
            raise RuntimeError(f"Failed during u-probability estimation: {exc}") from exc

        logger.info("Estimating probability two random records match...")
        try:
            self.linker.training.estimate_probability_two_random_records_match(
                [block_on("email"), block_on("zipcode")],
                recall=0.7,
            )
        except Exception as exc:
            logger.warning("Could not estimate p(match): %s", exc)

        logger.info("Training m-probabilities with EM algorithm...")
        for rule in [block_on("email"), block_on("zipcode")]:
            try:
                self.linker.training.estimate_parameters_using_expectation_maximisation(rule)
            except Exception as exc:
                logger.warning("EM training failed for rule '%s': %s", rule, exc)

        logger.info("Model training complete.")

    def find_matches(self) -> pd.DataFrame:
        """
        Generate match predictions from the trained model.

        Returns:
            DataFrame with one row per candidate pair above review_threshold.

        Raises:
            RuntimeError: If the model has not been trained or prediction fails.
        """
        if self.linker is None:
            raise RuntimeError("Model has not been trained. Call train_model() first.")

        logger.info("Finding matches...")
        try:
            predictions = self.linker.inference.predict(
                threshold_match_probability=self.review_threshold
            )
            matches_df = predictions.as_pandas_dataframe()
        except Exception as exc:
            raise RuntimeError(f"Failed during match prediction: {exc}") from exc

        logger.info(
            "Found %d potential matches above threshold %.2f",
            len(matches_df),
            self.review_threshold,
        )

        return matches_df

    def categorize_matches(self, matches_df: pd.DataFrame) -> dict:
        """
        Categorize matches into auto-merge and needs-review tiers.

        Args:
            matches_df: DataFrame with match predictions.

        Returns:
            Dictionary with 'auto_merge', 'needs_review', and 'total_matches'.
        """
        auto_merge = matches_df[matches_df["match_probability"] >= self.auto_merge_threshold]
        needs_review = matches_df[
            (matches_df["match_probability"] >= self.review_threshold)
            & (matches_df["match_probability"] < self.auto_merge_threshold)
        ]

        results = {
            "auto_merge": auto_merge,
            "needs_review": needs_review,
            "total_matches": len(matches_df),
        }

        logger.info("Match categorization:")
        logger.info("  Auto-merge  (>=%.2f): %d pairs", self.auto_merge_threshold, len(auto_merge))
        logger.info(
            "  Needs review (%.2f–%.2f): %d pairs",
            self.review_threshold,
            self.auto_merge_threshold,
            len(needs_review),
        )
        logger.info("  Total potential matches: %d pairs", len(matches_df))

        return results

    def validate_accuracy(
        self,
        matches_df: pd.DataFrame,
        shopify_df: pd.DataFrame,
        stripe_df: pd.DataFrame,
    ) -> dict:
        """
        Validate matching accuracy against ground truth true_customer_id labels.

        Args:
            matches_df: DataFrame with match predictions (not modified).
            shopify_df: Prepared Shopify records (with unique_id + true_customer_id).
            stripe_df:  Prepared Stripe records (with unique_id + true_customer_id).

        Returns:
            Dictionary with precision, recall, true/false positives, and total true pairs.
        """
        matches_df = matches_df.copy()  # never mutate the caller's DataFrame

        # Build unique_id → true_customer_id lookup from both platforms
        record_to_true_id = pd.concat([
            shopify_df[["unique_id", "true_customer_id"]],
            stripe_df[["unique_id", "true_customer_id"]],
        ]).set_index("unique_id")["true_customer_id"]

        matches_df["true_match"] = (
            matches_df["unique_id_l"].map(record_to_true_id)
            == matches_df["unique_id_r"].map(record_to_true_id)
        )

        total_matches = len(matches_df)
        true_positives = int(matches_df["true_match"].sum())
        false_positives = total_matches - true_positives

        # Total true pairs = customers who appear on both platforms
        shopify_cust_ids = set(shopify_df["true_customer_id"])
        stripe_cust_ids = set(stripe_df["true_customer_id"])
        total_true_pairs = len(shopify_cust_ids & stripe_cust_ids)

        precision = true_positives / total_matches if total_matches > 0 else 0
        recall = true_positives / total_true_pairs if total_true_pairs > 0 else 0

        # Metrics for auto-merge tier specifically
        auto_merge_matches = matches_df[
            matches_df["match_probability"] >= self.auto_merge_threshold
        ]
        auto_merge_precision = (
            auto_merge_matches["true_match"].sum() / len(auto_merge_matches)
            if len(auto_merge_matches) > 0
            else 0
        )

        metrics = {
            "overall_precision": precision,
            "overall_recall": recall,
            "auto_merge_precision": auto_merge_precision,
            "true_positives": true_positives,
            "false_positives": false_positives,
            "total_true_pairs": total_true_pairs,
            "total_predictions": total_matches,
        }

        logger.info("Validation results:")
        logger.info("  Overall precision:    %.2f%%", precision * 100)
        logger.info("  Overall recall:       %.2f%%", recall * 100)
        logger.info("  Auto-merge precision: %.2f%%", auto_merge_precision * 100)
        logger.info("  True positives:  %d / %d true pairs", true_positives, total_true_pairs)
        logger.info("  False positives: %d", false_positives)

        return metrics

    def save_results(self, results: dict, output_dir: str = "./") -> None:
        """
        Save matching results to CSV files and metrics to JSON.

        Args:
            results: Dictionary with categorized matches (and optionally 'metrics').
            output_dir: Directory to save output files.
        """
        auto_merge_path = os.path.join(output_dir, AUTO_MERGE_CSV)
        review_path = os.path.join(output_dir, REVIEW_QUEUE_CSV)

        results["auto_merge"].to_csv(auto_merge_path, index=False)
        results["needs_review"].to_csv(review_path, index=False)

        logger.info("Results saved:")
        logger.info("  %s (%d records)", auto_merge_path, len(results["auto_merge"]))
        logger.info("  %s (%d records)", review_path, len(results["needs_review"]))

        if "metrics" in results:
            metrics_path = os.path.join(output_dir, VALIDATION_METRICS_JSON)
            with open(metrics_path, "w") as f:
                json.dump(results["metrics"], f, indent=2)
            logger.info("  %s (validation metrics)", metrics_path)

    def run_full_pipeline(
        self, shopify_df: pd.DataFrame, stripe_df: pd.DataFrame
    ) -> dict:
        """
        Run the complete matching pipeline end-to-end.

        Args:
            shopify_df: Shopify customer records.
            stripe_df:  Stripe customer records.

        Returns:
            Dictionary with 'results', 'metrics', 'shopify_df', 'stripe_df',
            'combined_df', and 'matches_df'.
        """
        logger.info("=" * 60)
        logger.info("CUSTOMER RECORD MATCHING PIPELINE")
        logger.info("=" * 60)

        logger.info("Step 1: Preparing data...")
        shopify_prepped, stripe_prepped = self.prepare_data(shopify_df, stripe_df)

        logger.info("Step 2: Training matching model...")
        self.train_model(shopify_prepped, stripe_prepped)

        logger.info("Step 3: Finding matches...")
        matches_df = self.find_matches()

        logger.info("Step 4: Categorizing matches...")
        results = self.categorize_matches(matches_df)

        logger.info("Step 5: Validating accuracy...")
        metrics = self.validate_accuracy(matches_df, shopify_prepped, stripe_prepped)

        logger.info("Step 6: Saving results...")
        self.save_results({**results, "metrics": metrics})

        logger.info("=" * 60)
        logger.info("PIPELINE COMPLETE")
        logger.info("=" * 60)

        # combined_df is provided for callers that need a single lookup table
        combined_df = pd.concat([shopify_prepped, stripe_prepped], ignore_index=True)

        return {
            "results": results,
            "metrics": metrics,
            "shopify_df": shopify_prepped,
            "stripe_df": stripe_prepped,
            "combined_df": combined_df,
            "matches_df": matches_df,
        }


def main() -> dict:
    """Main execution function — accepts --hard-cases flag."""
    import argparse

    parser = argparse.ArgumentParser(description="Run the customer matching pipeline.")
    parser.add_argument(
        "--hard-cases",
        action="store_true",
        help="Use the hard-cases dataset variants (*_with_hard_cases.csv).",
    )
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

    from data import load_raw_data

    shopify_df, stripe_df = load_raw_data(use_hard_cases=args.hard_cases)

    matcher = CustomerMatcher(
        auto_merge_threshold=AUTO_MERGE_THRESHOLD,
        review_threshold=REVIEW_THRESHOLD,
    )

    pipeline_results = matcher.run_full_pipeline(shopify_df, stripe_df)

    logger.info("Sample auto-merge matches:")
    for _, row in pipeline_results["results"]["auto_merge"].head(3).iterrows():
        logger.info(
            "  prob=%.3f  left='%s | %s'  right='%s | %s'",
            row["match_probability"],
            row["name_l"], row["email_l"],
            row["name_r"], row["email_r"],
        )

    return pipeline_results


if __name__ == "__main__":
    results = main()
