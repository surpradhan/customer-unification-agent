"""
Central configuration for the Customer Unification Agent.

All thresholds, file paths, and tuning parameters live here.
Import from this module instead of using magic numbers inline.
"""

# ---------------------------------------------------------------------------
# Matching thresholds
# ---------------------------------------------------------------------------
AUTO_MERGE_THRESHOLD: float = 0.95   # Confidence above which records auto-merge
REVIEW_THRESHOLD: float = 0.75       # Confidence above which records go to review

# ---------------------------------------------------------------------------
# Splink training
# ---------------------------------------------------------------------------
MAX_PAIRS_RANDOM_SAMPLING: float = 1_000_000  # max_pairs for u-probability estimation

# ---------------------------------------------------------------------------
# Splink comparison thresholds
# ---------------------------------------------------------------------------
EMAIL_LEVENSHTEIN_THRESHOLDS: list[int] = [1, 2]
NAME_JARO_WINKLER_THRESHOLDS: list[float] = [0.9, 0.8]
PHONE_LEVENSHTEIN_THRESHOLDS: list[int] = [2, 5]
ADDRESS_LEVENSHTEIN_THRESHOLDS: list[int] = [5, 10]
EMAIL_BLOCKING_PREFIX_LEN: int = 6   # substr(email, 1, N) used in blocking rules

# ---------------------------------------------------------------------------
# Synthetic data generation
# ---------------------------------------------------------------------------
DEFAULT_N_CUSTOMERS: int = 500
DEFAULT_CROSS_PLATFORM_RATE: float = 0.70

VARIATION_PROBABILITIES: dict[str, float] = {
    "low": 0.3,
    "medium": 0.6,
    "high": 0.8,
}

# ---------------------------------------------------------------------------
# Hard case generation
# ---------------------------------------------------------------------------
DEFAULT_N_HARD_CASES: int = 20
# Cumulative thresholds for scenario assignment (i < A_THRESHOLD → Scenario A, etc.)
HARD_CASE_SCENARIO_A_THRESHOLD: float = 0.60
HARD_CASE_SCENARIO_B_THRESHOLD: float = 0.85  # Scenario C is the remainder (~15%)

# ---------------------------------------------------------------------------
# File paths
# ---------------------------------------------------------------------------
SHOPIFY_CSV: str = "shopify_customers.csv"
STRIPE_CSV: str = "stripe_customers.csv"
GROUND_TRUTH_CSV: str = "ground_truth.csv"

SHOPIFY_HARD_CSV: str = "shopify_customers_with_hard_cases.csv"
STRIPE_HARD_CSV: str = "stripe_customers_with_hard_cases.csv"
GROUND_TRUTH_HARD_CSV: str = "ground_truth_with_hard_cases.csv"

AUTO_MERGE_CSV: str = "auto_merge_matches.csv"
REVIEW_QUEUE_CSV: str = "review_queue_matches.csv"
VALIDATION_METRICS_JSON: str = "validation_metrics.json"

# ---------------------------------------------------------------------------
# Dashboard display
# ---------------------------------------------------------------------------
VALUE_BINS: list[int] = [0, 500, 1000, 2000, 3000, 5000, 10_000]
VALUE_BIN_LABELS: list[str] = ["$0-500", "$500-1K", "$1K-2K", "$2K-3K", "$3K-5K", "$5K+"]
VIP_SPEND_THRESHOLD: float = 2_000   # Customers above this total spend are VIPs
