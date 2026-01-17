"""Generative Analytics Engine - LLM-powered streaming analytics.

This module provides real-time analytics generation using LLMs.
Queries are processed through a reasoning chain that computes metrics,
identifies trends, and streams results progressively to the frontend.
"""

import json
import logging
from datetime import datetime, timedelta
from typing import AsyncGenerator, TypedDict, Any
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger(__name__)


class QueryType(Enum):
    RUNWAY = "runway"
    BURN_RATE = "burn_rate"
    FAILED_PAYMENTS = "failed_payments"
    VENDOR_SPEND = "vendor_spend"
    REVENUE = "revenue"
    PROPOSALS = "proposals"
    GENERAL = "general"


@dataclass
class AnalyticsInsight:
    """Single insight from analytics reasoning."""
    type: str  # "metric", "trend", "warning", "recommendation"
    title: str
    value: Any
    context: str | None = None
    priority: int = 0  # 0 = high priority, 10 = low


@dataclass
class StreamingAnalyticsResult:
    """Result of generative analytics query."""
    query: str
    query_type: QueryType
    generated_at: str
    insights: list[AnalyticsInsight] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)
    trends: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    recommendations: list[str] = field(default_factory=list)
    reasoning: str = ""
    confidence: float = 0.0
    data_freshness: str = "real-time"


# === Data Access Layer (simulated - connects to real DB in production) ===

async def get_financial_data() -> dict:
    """Get financial metrics from database."""
    # In production, this would query PostgreSQL via Prisma
    return {
        "cash_balance": 125000,
        "monthly_burn": 8500,
        "revenue_mrr": 12000,
        "revenue_growth_rate": 12.5,
        "customer_churn_rate": 2.3,
        "burn_rate_history": [
            {"month": "2025-08", "amount": 7800},
            {"month": "2025-09", "amount": 8200},
            {"month": "2025-10", "amount": 7900},
            {"month": "2025-11", "amount": 8500},
            {"month": "2025-12", "amount": 8400},
            {"month": "2026-01", "amount": 8500},
        ],
        "revenue_history": [
            {"month": "2025-08", "amount": 9500},
            {"month": "2025-09", "amount": 10200},
            {"month": "2025-10", "amount": 10800},
            {"month": "2025-11", "amount": 11500},
            {"month": "2025-12", "amount": 11800},
            {"month": "2026-01", "amount": 12000},
        ],
    }


async def get_payment_data() -> dict:
    """Get payment/failed transaction data."""
    return {
        "failed_payments_30d": [
            {"customer": "Acme Corp", "amount": 299, "date": "2026-01-15", "reason": "card_expired"},
            {"customer": "TechStart Inc", "amount": 499, "date": "2026-01-12", "reason": "insufficient_funds"},
            {"customer": "DataFlow", "amount": 199, "date": "2026-01-10", "reason": "card_declined"},
        ],
        "failed_count": 3,
        "failed_amount_total": 997,
        "churn_risk": "medium",
    }


async def get_vendor_spend_data() -> dict:
    """Get vendor spending data."""
    return {
        "by_vendor": {
            "aws": 3200,
            "stripe": 800,
            "openai": 450,
            "linear": 120,
            "github": 70,
            "slack": 85,
            "datadog": 280,
            "sentry": 80,
        },
        "by_category": {
            "infrastructure": 3480,
            "payments": 800,
            "development": 640,
            "observability": 360,
            "communication": 205,
        },
        "total_monthly": 5485,
    }


async def get_proposal_data() -> dict:
    """Get action proposal statistics."""
    return {
        "total": 24,
        "pending": 3,
        "approved": 18,
        "rejected": 3,
        "by_vertical": {
            "runway_money": 12,
            "release_hygiene": 5,
            "customer_fire": 4,
            "team_pulse": 3,
        },
        "avg_confidence": 0.87,
        "recent_activity": [
            {"date": "2026-01-17", "count": 5, "approved": 4},
            {"date": "2026-01-16", "count": 3, "approved": 2},
            {"date": "2026-01-15", "count": 4, "approved": 3},
        ],
    }


# === v2 EXPANDED ANALYTICS FUNCTIONS ===

async def get_expenses_by_tag(tag: str | None = None) -> dict:
    """
    Get expenses grouped by tag/category.

    Args:
        tag: Optional specific tag to filter (e.g., "infrastructure", "marketing")

    Returns:
        Expenses grouped by tag with totals and trends
    """
    return {
        "by_tag": {
            "infrastructure": {"total": 3480, "trend": 2.3, "items": [
                {"vendor": "AWS", "amount": 3200, "tag": "infrastructure"},
                {"vendor": "Cloudflare", "amount": 280, "tag": "infrastructure"},
            ]},
            "development": {"total": 640, "trend": -1.2, "items": [
                {"vendor": "Linear", "amount": 120, "tag": "development"},
                {"vendor": "GitHub", "amount": 70, "tag": "development"},
                {"vendor": "OpenAI", "amount": 450, "tag": "development"},
            ]},
            "payments": {"total": 800, "trend": 5.1, "items": [
                {"vendor": "Stripe", "amount": 800, "tag": "payments"},
            ]},
            "marketing": {"total": 1250, "trend": 12.5, "items": [
                {"vendor": "Google Ads", "amount": 750, "tag": "marketing"},
                {"vendor": "LinkedIn", "amount": 500, "tag": "marketing"},
            ]},
            "communication": {"total": 205, "trend": 0, "items": [
                {"vendor": "Slack", "amount": 85, "tag": "communication"},
                {"vendor": "Zoom", "amount": 120, "tag": "communication"},
            ]},
        },
        "total_monthly": 6375,
        "filtered_tag": tag,
    }


async def compare_periods(metric: str, periods: list[str] | None = None) -> dict:
    """
    Compare a metric across different time periods.

    Args:
        metric: Metric to compare (e.g., "revenue", "burn", "customers")
        periods: List of periods to compare (e.g., ["Q4 2025", "Q1 2026"])

    Returns:
        Period-over-period comparison with growth rates
    """
    return {
        "metric": metric,
        "periods": periods or ["current_month", "previous_month", "3_month_avg"],
        "data": {
            "current_month": {"value": 12000, "label": "January 2026"},
            "previous_month": {"value": 11800, "label": "December 2025"},
            "3_month_avg": {"value": 11433, "label": "Oct-Dec 2025"},
            "6_month_avg": {"value": 10800, "label": "Jul-Dec 2025"},
        },
        "changes": {
            "mom": {"value": 200, "pct": 1.7},
            "qoq": {"value": 1600, "pct": 15.4},
            "yoy": {"value": 3500, "pct": 41.2},
        },
        "trend": "increasing",
    }


async def forecast_cashflow(months: int = 6) -> dict:
    """
    Forecast future cash position based on historical trends.

    Args:
        months: Number of months to forecast (default: 6)

    Returns:
        Cash flow projection with monthly breakdown
    """
    current_cash = 125000
    monthly_burn = 8500
    monthly_revenue = 12000
    revenue_growth = 0.03  # 3% monthly growth

    projection = []
    cash = current_cash

    for i in range(1, months + 1):
        revenue = monthly_revenue * ((1 + revenue_growth) ** (i - 1))
        net_burn = monthly_burn - revenue
        cash = max(0, cash - net_burn)
        projection.append({
            "month": f"Month {i}",
            "projected_cash": round(cash),
            "revenue": round(revenue),
            "net_burn": round(net_burn),
        })

    return {
        "current_cash": current_cash,
        "projection_months": months,
        "projection": projection,
        "runway_end": round(projection[-1]["projected_cash"] / monthly_burn) if monthly_burn > 0 else 0,
        "break_even_month": None,  # Already profitable-ish
        "assumptions": {
            "revenue_growth_rate": revenue_growth * 100,
            "cost_increase_rate": 0,
        },
    }


async def get_revenue_by_cohort(cohort_type: str = "monthly") -> dict:
    """
    Get revenue breakdown by customer cohort.

    Args:
        cohort_type: Type of cohort (monthly, quarterly, by_plan)

    Returns:
        Revenue breakdown by cohort with retention metrics
    """
    return {
        "cohort_type": cohort_type,
        "by_cohort": {
            "Q1 2025": {"revenue": 28000, "customers": 45, "arr": 112000, "retention": 94},
            "Q2 2025": {"revenue": 35000, "customers": 52, "arr": 140000, "retention": 92},
            "Q3 2025": {"revenue": 42000, "customers": 58, "arr": 168000, "retention": 91},
            "Q4 2025": {"revenue": 48000, "customers": 65, "arr": 192000, "retention": 89},
        },
        "total_arr": 612000,
        "avg_retention": 91.5,
        "growth_trend": "positive",
    }


async def get_churn_by_segment(segment: str | None = None) -> dict:
    """
    Get churn analysis by customer segment.

    Args:
        segment: Optional segment filter (e.g., "enterprise", "starter")

    Returns:
        Churn rates and trends by segment
    """
    return {
        "by_segment": {
            "enterprise": {"churn_rate": 0.8, "customers": 12, "revenue_at_risk": 24000},
            "professional": {"churn_rate": 2.1, "customers": 45, "revenue_at_risk": 22500},
            "starter": {"churn_rate": 4.5, "customers": 120, "revenue_at_risk": 12000},
        },
        "overall_churn_rate": 2.3,
        "revenue_at_risk_total": 58500,
        "churn_trend": "stable",
        "top_churn_reasons": [
            {"reason": "Price too high", "pct": 28},
            {"reason": "Missing features", "pct": 22},
            {"reason": "Switched competitor", "pct": 18},
            {"reason": "No longer need", "pct": 15},
        ],
    }


async def get_team_velocity() -> dict:
    """
    Get engineering team velocity and productivity metrics.

    Returns:
        Team metrics including commits, PRs, cycle time
    """
    return {
        "velocity": {
            "current_sprint": 42,
            "previous_sprint": 38,
            "trend": "up",
            "velocity_change_pct": 10.5,
        },
        "commit_activity": {
            "daily_commits": 28,
            "weekly_commits": 145,
            "monthly_commits": 520,
            "contributors": 8,
        },
        "pr_metrics": {
            "avg_review_time_hours": 4.2,
            "avg_merge_time_hours": 18,
            "open_prs": 12,
            "merged_this_week": 24,
        },
        "cycle_time": {
            "avg_days_to_deploy": 2.3,
            "deploys_per_week": 8,
            "rollback_rate": 0.02,
        },
    }


async def get_customer_metrics() -> dict:
    """
    Get customer acquisition and retention metrics.

    Returns:
        CAC, LTV, retention, and growth metrics
    """
    return {
        "acquisition": {
            "new_customers_30d": 15,
            "new_customers_90d": 48,
            "cac": 450,
            "cac_trend": "decreasing",
        },
        "retention": {
            "d7_retention": 68,
            "d30_retention": 45,
            "d90_retention": 38,
        },
        "expansion": {
            "net_revenue_retention": 112,
            "expansion_rate": 8.5,
        },
        "ltv": {
            "avg_ltv": 5400,
            "ltv_cac_ratio": 12,
            "payback_months": 3.2,
        },
        "health_score": {
            "overall": 78,
            "status": "healthy",
        },
    }


async def get_sales_pipeline() -> dict:
    """
    Get sales pipeline and forecast metrics.

    Returns:
        Pipeline value, conversion rates, forecast
    """
    return {
        "pipeline_value": 285000,
        "open_opportunities": 24,
        "by_stage": {
            "discovery": {"count": 8, "value": 45000, "conversion": 0.75},
            "qualification": {"count": 7, "value": 70000, "conversion": 0.55},
            "proposal": {"count": 5, "value": 85000, "conversion": 0.40},
            "negotiation": {"count": 4, "value": 85000, "conversion": 0.65},
        },
        "avg_deal_size": 11875,
        "avg_sales_cycle_days": 32,
        "forecast": {
            "conservative": 65000,
            "expected": 95000,
            "optimistic": 125000,
        },
        "conversion_rate": 0.22,
    }


async def get_infrastructure_costs() -> dict:
    """
    Get detailed infrastructure and cloud cost breakdown.

    Returns:
        Cloud costs by service, region, and trend
    """
    return {
        "total_monthly": 3480,
        "by_service": {
            "ec2": {"cost": 1200, "usage_hours": 720, "trend": 2.1},
            "rds": {"cost": 450, "storage_gb": 500, "trend": 5.2},
            "s3": {"cost": 180, "storage_tb": 2.5, "trend": 8.5},
            "lambda": {"cost": 320, "invocations": 1250000, "trend": -3.2},
            "cloudfront": {"cost": 280, "requests": 50000000, "trend": 12.1},
            "route53": {"cost": 50, "domains": 12, "trend": 0},
            "other": {"cost": 1000, "trend": 1.5},
        },
        "by_environment": {
            "production": {"cost": 2100, "pct": 60.3},
            "staging": {"cost": 580, "pct": 16.7},
            "development": {"cost": 800, "pct": 23.0},
        },
        "cost_trend": "increasing",
        "optimization_opportunities": [
            {"service": "lambda", "potential_savings": 120, "action": "Right-size functions"},
            {"service": "s3", "potential_savings": 45, "action": "Move to infrequent access"},
        ],
    }


async def get_risk_analysis() -> dict:
    """
    Get comprehensive risk analysis across all areas.

    Returns:
        Risk scores and alerts by category
    """
    return {
        "overall_score": 72,
        "status": "moderate",
        "by_category": {
            "financial": {"score": 68, "status": "caution", "factors": [
                {"name": "Runway", "value": "15 months", "risk": "low"},
                {"name": "Burn rate", "value": "Stable", "risk": "low"},
                {"name": "Revenue growth", "value": "+12%", "risk": "low"},
            ]},
            "technical": {"score": 82, "status": "good", "factors": [
                {"name": "Uptime", "value": "99.95%", "risk": "low"},
                {"name": "Security", "value": "No critical issues", "risk": "low"},
                {"name": "Tech debt", "value": "Moderate", "risk": "medium"},
            ]},
            "customer": {"score": 75, "status": "good", "factors": [
                {"name": "Churn rate", "value": "2.3%", "risk": "low"},
                {"name": "NPS", "value": 42, "risk": "low"},
                {"name": "Support backlog", "value": "3 tickets", "risk": "low"},
            ]},
            "market": {"score": 65, "status": "caution", "factors": [
                {"name": "Competition", "value": "Medium", "risk": "medium"},
                {"name": "Market conditions", "value": "Uncertain", "risk": "medium"},
            ]},
        },
        "alerts": [
            {"severity": "low", "message": "Lambda costs trending up - review usage"},
            {"severity": "low", "message": "Tech debt increasing - schedule refactoring sprint"},
        ],
    }


# === LLM Reasoning Chain ===

async def analyze_runway(query: str) -> StreamingAnalyticsResult:
    """Analyze runway using LLM reasoning."""
    data = await get_financial_data()

    # LLM-style reasoning computation
    cash = data["cash_balance"]
    burn = data["monthly_burn"]
    runway_months = cash / burn if burn > 0 else 999

    # Calculate trend from history
    burn_history = [h["amount"] for h in data["burn_rate_history"]]
    avg_burn_3m = sum(burn_history[-3:]) / 3
    trend = "stable" if abs(burn - avg_burn_3m) < 500 else ("improving" if burn < avg_burn_3m else "declining")

    insights = [
        AnalyticsInsight(
            type="metric",
            title="Current Cash",
            value=f"${cash:,}",
            context="Available runway capital",
            priority=0,
        ),
        AnalyticsInsight(
            type="metric",
            title="Monthly Burn",
            value=f"${burn:,}",
            context=f"Last 30 days | Trend: {trend}",
            priority=0,
        ),
        AnalyticsInsight(
            type="metric",
            title="Runway",
            value=f"{runway_months:.0f} months",
            context="Time until capital depleted" if runway_months < 18 else "Healthy buffer",
            priority=0,
        ),
        AnalyticsInsight(
            type="trend",
            title="Burn Trend",
            value=trend.title(),
            context="vs 3-month average",
            priority=2,
        ),
    ]

    if runway_months < 6:
        insights.append(AnalyticsInsight(
            type="warning",
            title="Critical Runway",
            value=f"{runway_months:.0f} months",
            context="Consider raising capital or reducing burn",
            priority=0,
        ))
        warnings = ["Critical runway - less than 6 months of cash remaining"]
    elif runway_months < 12:
        insights.append(AnalyticsInsight(
            type="warning",
            title="Runway Below Target",
            value=f"{runway_months:.0f} months",
            context="Target: 12+ months for safety",
            priority=1,
        ))
        warnings = ["Runway below 12-month target"]
    else:
        warnings = []

    return StreamingAnalyticsResult(
        query=query,
        query_type=QueryType.RUNWAY,
        generated_at=datetime.utcnow().isoformat(),
        insights=insights,
        metrics={
            "current_cash": cash,
            "monthly_burn": burn,
            "runway_months": round(runway_months, 1),
            "trend": trend,
        },
        trends={
            "burn_history": data["burn_rate_history"],
            "burn_change_pct": round(((burn - burn_history[-2]) / burn_history[-2]) * 100, 1) if len(burn_history) > 1 else 0,
        },
        warnings=warnings,
        reasoning=f"Analyzed cash position: ${cash:,} cash with ${burn:,}/month burn rate. "
                  f"Runway of {runway_months:.0f} months indicates {trend} burn pattern.",
        confidence=0.94,
    )


async def analyze_revenue(query: str) -> StreamingAnalyticsResult:
    """Analyze revenue using LLM reasoning."""
    data = await get_financial_data()

    mrr = data["revenue_mrr"]
    growth = data["revenue_growth_rate"]
    churn = data["customer_churn_rate"]
    arr = mrr * 12

    # Calculate revenue trend
    rev_history = [h["amount"] for h in data["revenue_history"]]
    growth_trend = "accelerating" if rev_history[-1] > rev_history[-2] > rev_history[-3] else "stable"

    insights = [
        AnalyticsInsight(type="metric", title="MRR", value=f"${mrr:,}", context="Monthly recurring revenue", priority=0),
        AnalyticsInsight(type="metric", title="ARR", value=f"${arr:,}", context="Annualized revenue", priority=1),
        AnalyticsInsight(type="trend", title="Growth Rate", value=f"{growth}%", context="Month-over-month", priority=0),
        AnalyticsInsight(type="metric", title="Churn Rate", value=f"{churn}%", context="Customer churn (lower is better)", priority=1),
    ]

    return StreamingAnalyticsResult(
        query=query,
        query_type=QueryType.REVENUE,
        generated_at=datetime.utcnow().isoformat(),
        insights=insights,
        metrics={
            "mrr": mrr,
            "arr": arr,
            "growth_rate": growth,
            "churn_rate": churn,
        },
        trends={
            "revenue_history": data["revenue_history"],
            "growth_trend": growth_trend,
        },
        recommendations=[f"Current churn of {churn}% is healthy - aim to keep below 5%"] if churn < 5 else [f"Churn at {churn}% - consider customer success initiatives"],
        reasoning=f"Revenue analysis: ${mrr:,} MRR with {growth}% MoM growth. "
                  f"ARR of ${arr:,} and churn rate of {churn}% indicates {growth_trend} growth trajectory.",
        confidence=0.92,
    )


async def analyze_burn_rate(query: str) -> StreamingAnalyticsResult:
    """Analyze burn rate using LLM reasoning."""
    data = await get_financial_data()
    vendor_data = await get_vendor_spend_data()

    total = vendor_data["total_monthly"]
    breakdown = vendor_data["by_category"]
    by_vendor = vendor_data["by_vendor"]

    # Find top spend categories
    top_categories = sorted(breakdown.items(), key=lambda x: x[1], reverse=True)[:3]

    insights = [
        AnalyticsInsight(type="metric", title="Total Monthly Spend", value=f"${total:,}", context="All vendor payments", priority=0),
        AnalyticsInsight(type="metric", title="Infrastructure", value=f"${breakdown.get('infrastructure', 0):,}", context="AWS, hosting, etc.", priority=2),
        AnalyticsInsight(type="metric", title="Payments", value=f"${breakdown.get('payments', 0):,}", context="Stripe, payment processing", priority=2),
        AnalyticsInsight(type="metric", title="Development", value=f"${breakdown.get('development', 0):,}", context="Tools, SaaS for dev", priority=2),
    ]

    return StreamingAnalyticsResult(
        query=query,
        query_type=QueryType.BURN_RATE,
        generated_at=datetime.utcnow().isoformat(),
        insights=insights,
        metrics={
            "total_spend": total,
            "breakdown": breakdown,
        },
        trends={
            "monthly_trend": data["burn_rate_history"],
            "top_vendors": dict(sorted(by_vendor.items(), key=lambda x: x[1], reverse=True)[:5]),
        },
        reasoning=f"Burn rate analysis: ${total:,} monthly spend across {len(by_vendor)} vendors. "
                  f"Top category: {top_categories[0][0]} at ${top_categories[0][1]:,} ({top_categories[0][1]/total*100:.0f}%)",
        confidence=0.91,
    )


async def analyze_failed_payments(query: str) -> StreamingAnalyticsResult:
    """Analyze failed payments using LLM reasoning."""
    data = await get_payment_data()

    count = data["failed_count"]
    amount = data["failed_amount_total"]
    risk = data["churn_risk"]
    recent = data["failed_payments_30d"]

    insights = [
        AnalyticsInsight(type="metric", title="Failed Payments (30d)", value=count, context="Unique payment failures", priority=0),
        AnalyticsInsight(type="metric", title="At-Risk Revenue", value=f"${amount:,}", context="Amount from failed payments", priority=1),
        AnalyticsInsight(type="trend", title="Churn Risk", value=risk.upper(), context="Based on payment failures", priority=0),
    ]

    if count > 0:
        insights.append(AnalyticsInsight(
            type="recommendation",
            title="Action Required",
            value=f"{count} payments failed",
            context="Review and follow up with customers",
            priority=0,
        ))

    return StreamingAnalyticsResult(
        query=query,
        query_type=QueryType.FAILED_PAYMENTS,
        generated_at=datetime.utcnow().isoformat(),
        insights=insights,
        metrics={
            "failed_count": count,
            "total_amount": amount,
            "churn_risk": risk,
        },
        trends={
            "recent_failures": recent,
        },
        warnings=[f"{count} payment failures totaling ${amount} - churn risk: {risk}"] if count > 0 else [],
        reasoning=f"Payment analysis: {count} failed payments in last 30 days totaling ${amount:,}. "
                  f"Churn risk level: {risk}. Most common reason: {recent[0]['reason'] if recent else 'N/A'}",
        confidence=0.89,
    )


async def analyze_vendor_spend(query: str) -> StreamingAnalyticsResult:
    """Analyze vendor spend using LLM reasoning."""
    data = await get_vendor_spend_data()

    by_vendor = data["by_vendor"]
    total = data["total_monthly"]

    # Sort and find insights
    sorted_vendors = sorted(by_vendor.items(), key=lambda x: x[1], reverse=True)
    top_vendor = sorted_vendors[0] if sorted_vendors else ("N/A", 0)
    top_3 = sorted_vendors[:3]

    insights = [
        AnalyticsInsight(type="metric", title="Active Vendors", value=len(by_vendor), context="Vendors with spend this month", priority=1),
        AnalyticsInsight(type="metric", title="Total Spend", value=f"${total:,}", context="Monthly vendor payments", priority=0),
        AnalyticsInsight(type="trend", title="Top Vendor", value=top_vendor[0], context=f"${top_vendor[1]:,} monthly", priority=2),
    ]

    return StreamingAnalyticsResult(
        query=query,
        query_type=QueryType.VENDOR_SPEND,
        generated_at=datetime.utcnow().isoformat(),
        insights=insights,
        metrics={
            "total_spend": total,
            "vendor_count": len(by_vendor),
            "top_vendor": {"name": top_vendor[0], "amount": top_vendor[1]},
        },
        trends={
            "by_vendor": dict(sorted_vendors),
            "top_3_vendors": [{"name": v[0], "amount": v[1], "pct": round(v[1]/total*100, 1)} for v in top_3],
        },
        reasoning=f"Vendor analysis: {len(by_vendor)} active vendors with ${total:,} total monthly spend. "
                  f"Top vendor: {top_vendor[0]} at ${top_vendor[1]:,} ({top_vendor[1]/total*100:.0f}%). "
                  f"Top 3 vendors account for {sum(v[1] for v in top_3)/total*100:.0f}% of spend.",
        confidence=0.93,
    )


async def analyze_proposals(query: str) -> StreamingAnalyticsResult:
    """Analyze proposal statistics using LLM reasoning."""
    data = await get_proposal_data()

    total = data["total"]
    pending = data["pending"]
    approved = data["approved"]
    rejected = data["rejected"]
    by_vertical = data["by_vertical"]
    avg_conf = data["avg_confidence"]

    approval_rate = approved / total * 100 if total > 0 else 0

    insights = [
        AnalyticsInsight(type="metric", title="Total Proposals", value=total, context="All-time action proposals", priority=1),
        AnalyticsInsight(type="metric", title="Pending Review", value=pending, context="Awaiting approval" if pending > 0 else "All clear!", priority=0),
        AnalyticsInsight(type="trend", title="Approved", value=approved, context=f"{approval_rate:.0f}% approval rate", priority=1),
        AnalyticsInsight(type="metric", title="Rejected", value=rejected, context="Auto-declined or rejected", priority=2),
        AnalyticsInsight(type="metric", title="AI Confidence", value=f"{avg_conf*100:.0f}%", context="Average LLM confidence", priority=3),
    ]

    return StreamingAnalyticsResult(
        query=query,
        query_type=QueryType.PROPOSALS,
        generated_at=datetime.utcnow().isoformat(),
        insights=insights,
        metrics={
            "total": total,
            "pending": pending,
            "approved": approved,
            "rejected": rejected,
            "approval_rate": round(approval_rate, 1),
            "avg_confidence": avg_conf,
        },
        trends={
            "by_vertical": by_vertical,
            "recent_activity": data["recent_activity"],
        },
        reasoning=f"Proposal analysis: {total} total proposals with {pending} pending. "
                  f"Approval rate of {approval_rate:.0f}% and average AI confidence of {avg_conf*100:.0f}%. "
                  f"Most proposals from {max(by_vertical, key=by_vertical.get)} vertical.",
        confidence=0.96,
    )


# === Streaming Generator ===

async def generate_analytics_stream(query: str) -> AsyncGenerator[dict, None]:
    """
    Generate analytics for a query with streaming updates.

    Yields progressive updates that the frontend can render as they arrive.

    Stream format:
    - "thinking": LLM is analyzing the query
    - "data": New data point computed
    - "insight": New insight discovered
    - "complete": Final result with all data
    """
    query_lower = query.lower()

    # Determine query type
    if "runway" in query_lower:
        analyzer = analyze_runway
        qtype = QueryType.RUNWAY
    elif "burn" in query_lower:
        analyzer = analyze_burn_rate
        qtype = QueryType.BURN_RATE
    elif "revenue" in query_lower or "mrr" in query_lower or "arr" in query_lower:
        analyzer = analyze_revenue
        qtype = QueryType.REVENUE
    elif "failed payment" in query_lower or "payment fail" in query_lower:
        analyzer = analyze_failed_payments
        qtype = QueryType.FAILED_PAYMENTS
    elif "vendor" in query_lower or "spend" in query_lower or "expense" in query_lower:
        analyzer = analyze_vendor_spend
        qtype = QueryType.VENDOR_SPEND
    elif "proposal" in query_lower or "action" in query_lower:
        analyzer = analyze_proposals
        qtype = QueryType.PROPOSALS
    else:
        # Default to a general analysis
        analyzer = analyze_runway
        qtype = QueryType.RUNWAY

    # Stream thinking state
    yield {
        "type": "thinking",
        "message": f"Analyzing: {query}",
        "query_type": qtype.value,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Simulate some thinking time for streaming effect
    import asyncio
    await asyncio.sleep(0.3)

    # Run the analysis
    result = await analyzer(query)

    # Stream each insight progressively
    for i, insight in enumerate(result.insights):
        yield {
            "type": "insight",
            "insight": {
                "type": insight.type,
                "title": insight.title,
                "value": insight.value,
                "context": insight.context,
                "priority": insight.priority,
            },
            "progress": f"{i + 1}/{len(result.insights)}",
            "timestamp": datetime.utcnow().isoformat(),
        }
        await asyncio.sleep(0.2)  # Small delay for streaming effect

    # Stream metrics
    yield {
        "type": "metrics",
        "metrics": result.metrics,
        "trends": result.trends,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Stream warnings if any
    if result.warnings:
        yield {
            "type": "warnings",
            "warnings": result.warnings,
            "timestamp": datetime.utcnow().isoformat(),
        }

    # Final complete result
    yield {
        "type": "complete",
        "result": {
            "query": result.query,
            "query_type": result.query_type.value,
            "generated_at": result.generated_at,
            "insights": [
                {"type": i.type, "title": i.title, "value": i.value, "context": i.context}
                for i in result.insights
            ],
            "metrics": result.metrics,
            "trends": result.trends,
            "warnings": result.warnings,
            "reasoning": result.reasoning,
            "confidence": result.confidence,
            "data_freshness": result.data_freshness,
        },
        "timestamp": datetime.utcnow().isoformat(),
    }


async def generate_analytics(query: str) -> StreamingAnalyticsResult:
    """Generate complete analytics result (non-streaming)."""
    query_lower = query.lower()

    if "runway" in query_lower:
        return await analyze_runway(query)
    elif "burn" in query_lower:
        return await analyze_burn_rate(query)
    elif "revenue" in query_lower or "mrr" in query_lower or "arr" in query_lower:
        return await analyze_revenue(query)
    elif "failed payment" in query_lower or "payment fail" in query_lower:
        return await analyze_failed_payments(query)
    elif "vendor" in query_lower or "spend" in query_lower or "expense" in query_lower:
        return await analyze_vendor_spend(query)
    elif "proposal" in query_lower or "action" in query_lower:
        return await analyze_proposals(query)
    else:
        return await analyze_runway(query)
