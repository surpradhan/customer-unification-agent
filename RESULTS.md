# Customer Unification Agent — Results

Numbers produced by Splink 4.0.16 with `link_type="link_only"`.  
Re-run `python matching_engine.py [--hard-cases]` to refresh.

---

## Dataset

| | Count |
|---|---|
| Shopify records | 425 |
| Stripe records | 425 |
| **Total records** | **850** |
| Unique customers (ground truth) | 500 |
| True cross-platform customers | 350 (70%) |

The synthetic dataset introduces realistic noise: name abbreviations ("Lisa Martinez" → "L Martinez"), reversed tokens ("Joseph Campbell" → "Campbell Joseph"), phone reformatting, email `+alias` variants, and apartment-number differences in addresses.

---

## Matching Results — Baseline (no hard cases)

### Auto-merge tier (≥ 95% confidence)

| Metric | Value |
|---|---|
| Pairs surfaced | 341 |
| True positives | 341 |
| **False positives** | **0** |
| **Precision** | **100%** |
| **Recall** | **97.4%** (341 / 350 true pairs) |

### Review queue tier (75 – 95% confidence)

| Metric | Value |
|---|---|
| Pairs flagged for human review | 9 |
| True positives in queue | 9 (100%) |

The 9 review-queue pairs all share the same zipcode and name (reversed or abbreviated) but have changed email domains or `+alias` suffixes — the email comparison falls to `gamma=0`, so the model correctly hedges rather than auto-merging.

### Combined (both tiers, ≥ 75%)

| Metric | Value |
|---|---|
| Total true pairs captured | **350 / 350** |
| **Overall recall** | **100%** |
| **Overall precision** | **100%** |
| False positives | 0 |
| False negatives | 0 |

---

## Matching Results — With Hard Cases (+20 tricky pairs)

Hard cases include: email domain change + address move (Scenario A), name change after marriage + email change (Scenario B), and name-only match with everything else different (Scenario C).

| Metric | Value |
|---|---|
| True cross-platform pairs | 370 (350 base + 20 hard) |
| Auto-merge pairs | 356 |
| Auto-merge precision | **99.7%** |
| Review queue pairs | 19 |
| True positives (both tiers) | 355 |
| False positives | 20 |
| **Overall recall** | **95.9%** |
| **Overall precision** | **94.7%** |

The 15 missed hard-case pairs are Scenario C (name-only match, completely different email, phone, and address) — they don't pass any blocking rule and are genuinely ambiguous without external signals.

---

## Why These Results Improved Over the v3 Run

The original v3 run used `link_type="dedupe_only"` on a merged DataFrame. This generated candidate pairs *within* each platform, producing **42 false positives** (36 same-platform, 6 cross-platform) and an 89% auto-merge precision. Switching to `link_type="link_only"` with separate DataFrames eliminates the entire same-platform candidate class structurally, bringing precision to 100% on the baseline set.

---

## Algorithm Tradeoff: Why Jaro-Winkler for Names, Levenshtein for Email

### Email → Levenshtein distance

Email addresses are **structured strings with a fixed schema** (`local@domain`). Errors are almost always mechanical: a missing character, a transposed digit, or a punctuation difference (`+` alias, `.` omitted). Levenshtein edit distance captures these precisely because each operation has equal cost and the total distance is interpretable — a distance of 1 means exactly one character changed.

Jaro-Winkler would be wrong here: it rewards common prefixes, which means `johnsmith@gmail.com` and `johnstone@gmail.com` score very highly even though they belong to different people. Email local-parts are not names; prefix similarity is noise, not signal.

Threshold choice — `[1, 2]` — is intentionally tight. Email is the strongest identity signal; loosening it admits false positives. A distance-1 edit covers the most common real-world variation (a missing `.`); distance-2 covers `+alias` suffixes that are still 7–8 characters — but because those pairs are blocked by the 6-char prefix rule, they still become candidates and are resolved by the other comparison signals.

### Names → Jaro-Winkler similarity

Names are **fuzzy, prefix-heavy strings** with predictable variation patterns:
- Initials: "Lisa Martinez" → "L Martinez"
- Reversed tokens: "Clark Anthony" → "Anthony Clark"
- Spacing artefacts: "NicoleTaylor" → "Nicole Taylor"

Jaro-Winkler is well-suited because it:
1. Gives extra weight to matching prefixes — "L" correctly echoes the start of "Lisa".
2. Penalises transpositions less harshly than substitutions — handles reversed-token names naturally.
3. Produces a similarity in [0, 1] that is semantically meaningful for human names (0.9+ = same person).

Levenshtein would be wrong here: "Lisa Martinez" vs "L Martinez" has an edit distance of 8, far outside any reasonable threshold, yet these records are the same person.

Threshold choice — `[0.9, 0.8]` — creates two Bayes-factor tiers. Above 0.9 name similarity contributes strongly; 0.8–0.9 contributes a weaker positive signal. Below 0.8 the name is treated as a non-match.

---

## Splink v4 Migration

Migrated from Splink 3.9.10 to Splink 4.0.16.

| | Splink 3.x | Splink 4.x |
|---|---|---|
| Linker class | `DuckDBLinker(df, settings_dict)` | `Linker([df1, df2], settings, db_api=DuckDBAPI())` |
| Settings | plain `dict` | `SettingsCreator(...)` |
| Link type | `"dedupe_only"` on merged df | `"link_only"` with separate platform dfs |
| Comparisons | `levenshtein_at_thresholds(...)` | `cl.LevenshteinAtThresholds(...).configure(...)` |
| u-training | `linker.estimate_u_using_random_sampling()` | `linker.training.estimate_u_using_random_sampling()` |
| Prior calibration | not called (defaulted to 0.0001) | `linker.training.estimate_probability_two_random_records_match()` |
| EM training | `linker.estimate_parameters_using_expectation_maximisation()` | `linker.training.estimate_parameters_using_expectation_maximisation()` |
| Prediction | `linker.predict(...)` | `linker.inference.predict(...)` |
| Blocking helpers | raw SQL strings only | `block_on("field")` + SQL strings |
