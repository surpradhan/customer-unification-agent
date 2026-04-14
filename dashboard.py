"""
ROI Dashboard for Customer Unification Agent
Shows the business value of merging duplicate customer records
"""

import json
import logging
import re

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    AUTO_MERGE_THRESHOLD,
    REVIEW_QUEUE_CSV,
    VALIDATION_METRICS_JSON,
    VALUE_BINS,
    VALUE_BIN_LABELS,
)
from data import load_dashboard_data, load_matches
from metrics import calculate_summary_metrics, vip_count

DASHBOARD_STATE_JSON = "dashboard_state.json"

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _load_precision() -> float | None:
    """Load precision from validation_metrics.json if it exists."""
    try:
        with open(VALIDATION_METRICS_JSON) as f:
            data = json.load(f)
        return data.get("overall_precision")
    except FileNotFoundError:
        return None


def _load_prev_metrics() -> dict | None:
    """Load metrics saved from the previous default-threshold run."""
    try:
        with open(DASHBOARD_STATE_JSON) as f:
            return json.load(f)
    except FileNotFoundError:
        return None


def _save_metrics(metrics: dict) -> None:
    """Persist key metrics so the next run can show deltas."""
    state = {
        k: metrics[k]
        for k in ("total_records", "duplicates_found", "unique_customers", "hidden_value", "precision")
        if k in metrics
    }
    try:
        with open(DASHBOARD_STATE_JSON, "w") as f:
            json.dump(state, f)
    except OSError as e:
        logger.warning("Could not save dashboard state: %s", e)


def _load_all_matches() -> pd.DataFrame:
    """Return auto-merge + review-queue matches combined (review-queue is optional)."""
    auto_df = load_matches()
    try:
        review_df = load_matches(REVIEW_QUEUE_CSV)
        combined = pd.concat([auto_df, review_df], ignore_index=True)
        return combined.drop_duplicates(subset=["unique_id_l", "unique_id_r"])
    except FileNotFoundError:
        return auto_df


def _normalize_names(series: pd.Series) -> pd.Series:
    """Insert spaces in CamelCase names (e.g. 'AnitaHunt' → 'Anita Hunt')."""
    return series.str.replace(r"(?<=[a-z])(?=[A-Z])", " ", regex=True)


def _drill_down_col_config() -> dict:
    return {
        "Shopify Spent": st.column_config.NumberColumn(format="$%.2f"),
        "Stripe Value": st.column_config.NumberColumn(format="$%.2f"),
        "Total Value": st.column_config.NumberColumn(format="$%.2f"),
        "Confidence": st.column_config.NumberColumn(format="%.1f%%"),
    }


# ---------------------------------------------------------------------------
# Sidebar
# ---------------------------------------------------------------------------

def render_sidebar(all_matches_df: pd.DataFrame) -> tuple[float, str]:
    """Render sidebar navigation, confidence slider, and platform filter.

    Returns (threshold, platform_filter).
    """
    with st.sidebar:
        st.markdown("## Navigation")
        st.markdown(
            """
<a href="#summary-metrics">📊 &nbsp;Summary Metrics</a><br>
<a href="#hidden-value">💰 &nbsp;Hidden Value</a><br>
<a href="#top-customers">🏆 &nbsp;Top Customers</a><br>
<a href="#value-distribution">📈 &nbsp;Value Distribution</a><br>
<a href="#actionable-insights">💡 &nbsp;Actionable Insights</a><br>
<a href="#match-quality">🎯 &nbsp;Match Quality</a>
            """,
            unsafe_allow_html=True,
        )

        st.divider()
        st.markdown("## Filters")

        min_conf = round(float(all_matches_df["match_probability"].min()), 2)
        threshold = st.slider(
            "Confidence Threshold",
            min_value=min_conf,
            max_value=1.0,
            value=max(min_conf, AUTO_MERGE_THRESHOLD),
            step=0.01,
            format="%.2f",
            help="Show only matches at or above this confidence level",
        )

        platform = st.selectbox(
            "Customer Type",
            ["All", "Shopify Primary", "Stripe Primary"],
            help="Filter by which platform drives more of the customer's spend",
        )

        st.caption(f"Showing matches ≥ {threshold:.0%} confidence")

    return threshold, platform


# ---------------------------------------------------------------------------
# Section renderers
# ---------------------------------------------------------------------------

def create_summary_cards(metrics: dict, prev: dict | None) -> None:
    """Display hero metrics with optional vs-last-run deltas."""
    st.markdown('<a id="summary-metrics"></a>', unsafe_allow_html=True)

    def _delta(key: str, fmt=lambda v: f"{v:+,}") -> str | None:
        if prev and prev.get(key) is not None:
            diff = metrics[key] - prev[key]
            if diff != 0:
                return fmt(diff)
        return None

    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Customer Records",
            f"{metrics['total_records']:,}",
            delta=_delta("total_records"),
            help="Combined records across Shopify and Stripe",
        )
    with col2:
        reduction = metrics["duplicates_found"] / metrics["total_records"] * 100
        st.metric(
            "Duplicates Found",
            f"{metrics['duplicates_found']:,}",
            delta=f"-{reduction:.1f}% reduction",
            delta_color="inverse",
            help="Number of duplicate customer records identified",
        )
    with col3:
        st.metric(
            "Unique Customers",
            f"{metrics['unique_customers']:,}",
            delta=_delta("unique_customers"),
            help="Actual number of unique customers after deduplication",
        )
    with col4:
        precision = metrics["precision"]
        precision_label = f"{precision:.1%}" if precision is not None else "N/A"
        st.metric(
            "Match Precision",
            precision_label,
            help="Accuracy of auto-merged matches (from validation run)",
        )


def create_value_unlock_section(metrics: dict, prev: dict | None) -> None:
    """Show hidden CLV with vs-last-run delta and Shopify/Stripe revenue split."""
    st.markdown('<a id="hidden-value"></a>', unsafe_allow_html=True)
    st.header("Hidden Value Unlocked")

    col1, col2 = st.columns([2, 1])

    with col1:
        hidden_delta = None
        if prev and prev.get("hidden_value") is not None:
            diff = metrics["hidden_value"] - prev["hidden_value"]
            if diff != 0:
                hidden_delta = f"${diff:+,.2f} vs last run"

        st.metric(
            "Combined Customer Lifetime Value",
            f"${metrics['hidden_value']:,.2f}",
            delta=hidden_delta,
            help="Total spending across both platforms that was previously invisible",
        )
        st.markdown(
            f"""
            **Before unification:** You saw these {metrics['duplicates_found']} customers as
            separate individuals with separate purchase histories.

            **After unification:** You now see their complete relationship with your business
            across all platforms.
            """
        )

    with col2:
        n = metrics["duplicates_found"]
        avg_value = metrics["hidden_value"] / n if n > 0 else 0
        st.metric("Avg Value Per Unified Customer", f"${avg_value:,.2f}")

        cp = metrics["cross_platform_customers"]
        if not cp.empty:
            shopify_total = float(cp["shopify_spent"].sum())
            stripe_total = float(cp["stripe_value"].sum())
            fig = go.Figure(data=[
                go.Bar(name="Shopify", x=["Revenue"], y=[shopify_total], marker_color="#5b9bd5"),
                go.Bar(name="Stripe", x=["Revenue"], y=[stripe_total], marker_color="#7b68ee"),
            ])
            fig.update_layout(
                barmode="stack",
                height=220,
                margin=dict(l=0, r=0, t=40, b=0),
                title_text="Platform Revenue Split",
                title_font_size=13,
                showlegend=True,
                legend=dict(orientation="h", y=1.18, x=0),
                yaxis_tickprefix="$",
                yaxis_tickformat=",.0f",
            )
            st.plotly_chart(fig, use_container_width=True)


def create_top_customers_table(cross_platform_df: pd.DataFrame) -> None:
    """Top customers table with search, show-all expander, and CSV download."""
    st.markdown('<a id="top-customers"></a>', unsafe_allow_html=True)
    st.header("Top Cross-Platform Customers")

    all_customers = cross_platform_df.sort_values("total_value", ascending=False).copy()

    search = st.text_input(
        "Search by name or email",
        placeholder="e.g. Jenny or @example.com",
        label_visibility="collapsed",
    )

    display_cols = ["name", "email", "shopify_spent", "stripe_value", "total_value", "match_confidence"]
    col_labels = ["Name", "Email", "Shopify Spent", "Stripe Value", "Total Value", "Confidence"]

    if search:
        mask = (
            all_customers["name"].str.contains(search, case=False, na=False)
            | all_customers["email"].str.contains(search, case=False, na=False)
        )
        display_df = all_customers[mask][display_cols].copy()
        display_df.columns = col_labels
    else:
        display_df = all_customers.head(10)[display_cols].copy()
        display_df.columns = col_labels

    st.dataframe(
        display_df,
        use_container_width=True,
        hide_index=True,
        column_config=_drill_down_col_config(),
    )

    btn_col, exp_col = st.columns([1, 3])
    with btn_col:
        csv = display_df.to_csv(index=False).encode("utf-8")
        st.download_button(
            "⬇️ Download CSV",
            data=csv,
            file_name="top_cross_platform_customers.csv",
            mime="text/csv",
        )

    if not search:
        with exp_col:
            with st.expander(f"Show all {len(all_customers)} matched customers"):
                all_display = all_customers[display_cols].copy()
                all_display.columns = col_labels
                st.dataframe(
                    all_display,
                    use_container_width=True,
                    hide_index=True,
                    column_config=_drill_down_col_config(),
                )
                full_csv = all_display.to_csv(index=False).encode("utf-8")
                st.download_button(
                    "⬇️ Download all customers",
                    data=full_csv,
                    file_name="all_cross_platform_customers.csv",
                    mime="text/csv",
                    key="dl_all",
                )

    st.markdown(
        "**Insight:** These are your most valuable cross-platform customers. "
        "They trust you enough to buy from multiple channels. Prioritize keeping them happy!"
    )


def create_distribution_chart(cross_platform_df: pd.DataFrame) -> None:
    """Bar chart of customer value distribution with drill-down by range selector."""
    st.markdown('<a id="value-distribution"></a>', unsafe_allow_html=True)
    st.header("Customer Value Distribution")

    binned = cross_platform_df.copy()
    binned["value_range"] = pd.cut(
        binned["total_value"],
        bins=VALUE_BINS,
        labels=VALUE_BIN_LABELS,
        include_lowest=True,
    )
    value_counts = binned["value_range"].value_counts().sort_index()

    fig = px.bar(
        x=value_counts.index,
        y=value_counts.values,
        labels={"x": "Customer Lifetime Value Range", "y": "Number of Customers"},
        title="Distribution of Unified Customer Values",
        color=value_counts.values,
        color_continuous_scale="Blues",
    )
    fig.update_layout(showlegend=False, height=400, coloraxis_showscale=False)
    st.plotly_chart(fig, use_container_width=True)

    # Drill-down via radio selector
    bin_labels = value_counts.index.tolist()
    bin_counts = {label: int(value_counts[label]) for label in bin_labels}
    options = ["(none)"] + [f"{lbl} ({bin_counts[lbl]} customers)" for lbl in bin_labels]

    selected_option = st.radio(
        "Explore a range:",
        options,
        horizontal=True,
        label_visibility="visible",
        key="distribution_bin_selector",
    )

    if selected_option != "(none)":
        # Extract just the label part before the " (" count
        selected_bin = selected_option.split(" (")[0]
        if selected_bin in binned["value_range"].cat.categories.tolist():
            bin_customers = binned[binned["value_range"] == selected_bin].sort_values(
                "total_value", ascending=False
            ).copy()

            st.markdown(f"**{len(bin_customers)} customers in the {selected_bin} range:**")

            display_cols = ["name", "email", "shopify_spent", "stripe_value", "total_value", "match_confidence"]
            drill_df = bin_customers[display_cols].copy()
            drill_df.columns = ["Name", "Email", "Shopify Spent", "Stripe Value", "Total Value", "Confidence"]

            st.dataframe(
                drill_df,
                use_container_width=True,
                hide_index=True,
                column_config=_drill_down_col_config(),
            )
            safe_key = re.sub(r"[^a-zA-Z0-9]", "_", selected_bin)
            csv = drill_df.to_csv(index=False).encode("utf-8")
            st.download_button(
                f"⬇️ Download {selected_bin} customers",
                data=csv,
                file_name=f"customers_{safe_key}.csv",
                mime="text/csv",
                key=f"dl_bin_{safe_key}",
            )


def create_insights_section(cross_platform_df: pd.DataFrame) -> None:
    """Actionable business insights cards."""
    st.markdown('<a id="actionable-insights"></a>', unsafe_allow_html=True)
    st.header("Actionable Insights")

    num_vip = vip_count(cross_platform_df)
    num_with_stripe = int((cross_platform_df["stripe_value"] > 0).sum())

    col1, col2 = st.columns(2)
    with col1:
        st.success(
            f"**Retargeting Opportunity**\n\n"
            f"{num_vip} customers have spent over $2,000 across both platforms. "
            f"These are your VIPs — create a loyalty program or exclusive offers for them."
        )
    with col2:
        st.info(
            f"**Cross-Sell Campaign**\n\n"
            f"{num_with_stripe} customers have Stripe charges AND make Shopify purchases. "
            f"They're highly engaged — what else can you sell them?"
        )


def create_match_quality_section(matches_df: pd.DataFrame, threshold: float) -> None:
    """Match quality histogram with threshold annotation."""
    st.markdown('<a id="match-quality"></a>', unsafe_allow_html=True)
    st.header("Match Quality")

    col1, col2 = st.columns([2, 1])

    with col1:
        min_prob = float(matches_df["match_probability"].min())
        fig = go.Figure(data=[go.Histogram(
            x=matches_df["match_probability"],
            xbins=dict(start=min_prob - 0.005, end=1.001, size=0.005),
            marker_color="rgb(55, 83, 109)",
        )])
        fig.add_vline(
            x=threshold,
            line_dash="dash",
            line_color="rgba(255, 165, 0, 0.85)",
            annotation_text=f"Threshold ({threshold:.0%})",
            annotation_position="top left",
            annotation_font_color="rgba(255, 165, 0, 0.95)",
        )
        fig.update_layout(
            title="Distribution of Match Confidence Scores",
            xaxis_title="Match Probability",
            yaxis_title="Number of Matches",
            height=300,
        )
        st.plotly_chart(fig, use_container_width=True)

    with col2:
        st.markdown(
            f"""
            **Match Statistics:**

            - Average confidence: {matches_df['match_probability'].mean():.1%}
            - Median confidence: {matches_df['match_probability'].median():.1%}
            - Min confidence: {matches_df['match_probability'].min():.1%}
            """
        )


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> None:
    st.set_page_config(
        page_title="Customer Unification Dashboard",
        page_icon="📊",
        layout="wide",
    )

    st.title("Customer Unification Dashboard")
    st.markdown("### Discover the hidden value in your customer data")

    with st.spinner("Loading customer data…"):
        try:
            shopify_df, stripe_df, _, _ = load_dashboard_data()
            all_matches_df = _load_all_matches()
        except FileNotFoundError as e:
            st.error(f"Data files not found. Please run the matching engine first. Error: {e}")
            return
        except ValueError as e:
            st.error(f"Data validation error: {e}")
            return

    # Sidebar: navigation + filters
    threshold, platform = render_sidebar(all_matches_df)

    # Filter matches by threshold
    matches_df = all_matches_df[all_matches_df["match_probability"] >= threshold].copy()

    # Calculate metrics
    precision = _load_precision()
    metrics = calculate_summary_metrics(shopify_df, stripe_df, matches_df, precision=precision)
    prev_metrics = _load_prev_metrics()

    # Apply platform filter and normalise display fields once, before passing to renderers
    cp = metrics["cross_platform_customers"].copy()
    if platform == "Shopify Primary":
        cp = cp[cp["shopify_spent"] >= cp["stripe_value"]]
    elif platform == "Stripe Primary":
        cp = cp[cp["stripe_value"] > cp["shopify_spent"]]
    cp["name"] = _normalize_names(cp["name"])
    cp["match_confidence"] = cp["match_confidence"] * 100
    metrics["cross_platform_customers"] = cp

    # Persist baseline metrics (only at the default threshold to keep a stable baseline)
    if abs(threshold - AUTO_MERGE_THRESHOLD) < 0.001:
        _save_metrics(metrics)

    # Render all sections
    create_summary_cards(metrics, prev_metrics)
    st.divider()

    create_value_unlock_section(metrics, prev_metrics)
    st.divider()

    if not cp.empty:
        create_top_customers_table(cp)
        st.divider()
        create_distribution_chart(cp)
        st.divider()
        create_insights_section(cp)

    st.divider()
    create_match_quality_section(matches_df, threshold)

    st.divider()
    precision_note = f"{precision:.1%}" if precision is not None else "run matching engine to compute"
    st.markdown(
        f"""
        **About this analysis:**
        - Matching algorithm: Probabilistic record linkage with {threshold:.0%} confidence threshold
        - Precision: {precision_note} (validated against ground truth)
        - Auto-merged: All matches with ≥{threshold:.0%} confidence
        """
    )


if __name__ == "__main__":
    main()
