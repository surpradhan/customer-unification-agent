"""
ROI Dashboard for Customer Unification Agent
Shows the business value of merging duplicate customer records
"""

import json
import logging

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import VALUE_BINS, VALUE_BIN_LABELS, VALIDATION_METRICS_JSON
from data import load_dashboard_data
from metrics import calculate_summary_metrics, top_customers, vip_count

logger = logging.getLogger(__name__)


def _load_precision() -> float | None:
    """Load precision from validation_metrics.json if it exists."""
    try:
        with open(VALIDATION_METRICS_JSON) as f:
            data = json.load(f)
        return data.get("overall_precision")
    except FileNotFoundError:
        return None


def create_summary_cards(metrics: dict) -> None:
    """Display hero metrics at the top of the dashboard."""
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric(
            "Total Customer Records",
            f"{metrics['total_records']:,}",
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


def create_value_unlock_section(metrics: dict) -> None:
    """Show the hidden value unlocked."""
    st.header("Hidden Value Unlocked")

    col1, col2 = st.columns([2, 1])

    with col1:
        st.metric(
            "Combined Customer Lifetime Value",
            f"${metrics['hidden_value']:,.2f}",
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


def create_top_customers_table(cross_platform_df: pd.DataFrame) -> None:
    """Show top cross-platform customers."""
    st.header("Top Cross-Platform Customers")

    display_df = top_customers(cross_platform_df, n=10)[
        ["name", "email", "shopify_spent", "stripe_value", "total_value", "match_confidence"]
    ].copy()

    display_df["shopify_spent"] = display_df["shopify_spent"].map("${:,.2f}".format)
    display_df["stripe_value"] = display_df["stripe_value"].map("${:,.2f}".format)
    display_df["total_value"] = display_df["total_value"].map("${:,.2f}".format)
    display_df["match_confidence"] = display_df["match_confidence"].map("{:.1%}".format)

    display_df.columns = ["Name", "Email", "Shopify Spent", "Stripe Value", "Total Value", "Confidence"]

    st.dataframe(display_df, use_container_width=True, hide_index=True)

    st.markdown(
        "**Insight:** These are your most valuable cross-platform customers. "
        "They trust you enough to buy from multiple channels. Prioritize keeping them happy!"
    )


def create_distribution_chart(cross_platform_df: pd.DataFrame) -> None:
    """Create value distribution visualization."""
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
    fig.update_layout(showlegend=False, height=400)

    st.plotly_chart(fig, use_container_width=True)


def create_insights_section(cross_platform_df: pd.DataFrame) -> None:
    """Generate actionable business insights."""
    st.header("Actionable Insights")

    num_vip = vip_count(cross_platform_df)
    num_active_subs = int((cross_platform_df["stripe_value"] > 0).sum())

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
            f"{num_active_subs} customers have active Stripe subscriptions AND make Shopify "
            f"purchases. They're highly engaged — what else can you sell them?"
        )


def create_match_quality_section(matches_df: pd.DataFrame) -> None:
    """Show match quality distribution."""
    st.header("Match Quality")

    col1, col2 = st.columns([2, 1])

    with col1:
        fig = go.Figure(data=[go.Histogram(
            x=matches_df["match_probability"],
            nbinsx=20,
            marker_color="rgb(55, 83, 109)",
        )])
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


def main() -> None:
    st.set_page_config(
        page_title="Customer Unification Dashboard",
        page_icon="",
        layout="wide",
    )

    st.title("Customer Unification Dashboard")
    st.markdown("### Discover the hidden value in your customer data")

    try:
        shopify_df, stripe_df, matches_df, _ = load_dashboard_data()
    except FileNotFoundError as e:
        st.error(f"Data files not found. Please run the matching engine first. Error: {e}")
        return
    except ValueError as e:
        st.error(f"Data validation error: {e}")
        return

    precision = _load_precision()
    metrics = calculate_summary_metrics(shopify_df, stripe_df, matches_df, precision=precision)

    create_summary_cards(metrics)
    st.divider()

    create_value_unlock_section(metrics)
    st.divider()

    cp = metrics["cross_platform_customers"]
    if not cp.empty:
        create_top_customers_table(cp)
        st.divider()
        create_distribution_chart(cp)
        st.divider()
        create_insights_section(cp)

    st.divider()
    create_match_quality_section(matches_df)

    st.divider()
    precision_note = f"{precision:.1%}" if precision is not None else "run matching engine to compute"
    st.markdown(
        f"""
        ---
        **About this analysis:**
        - Matching algorithm: Probabilistic record linkage with 95% confidence threshold
        - Precision: {precision_note} (validated against ground truth)
        - Auto-merged: All matches with >=95% confidence
        """
    )


if __name__ == "__main__":
    main()
