"""Generative Analytics Engine - v2 with expanded function library."""

from .generator import (
    generate_analytics,
    generate_analytics_stream,
    StreamingAnalyticsResult,
    AnalyticsInsight,
    QueryType,
    # v2 expanded functions
    get_financial_data,
    get_payment_data,
    get_vendor_spend_data,
    get_proposal_data,
    get_expenses_by_tag,
    compare_periods,
    forecast_cashflow,
    get_revenue_by_cohort,
    get_churn_by_segment,
    get_team_velocity,
    get_customer_metrics,
    get_sales_pipeline,
    get_infrastructure_costs,
    get_risk_analysis,
)

from .query_router import (
    route_query,
    generate_generative_ui_stream,
    QueryIntent,
    FunctionCall,
)

from .llm_router import (
    generate_true_generative_ui_stream,
    analyze_query_with_llm,
    LLMFunctionCall,
    UIComponent,
    ANALYTICS_FUNCTIONS,
)

__all__ = [
    # Core streaming
    "generate_analytics",
    "generate_analytics_stream",
    "StreamingAnalyticsResult",
    "AnalyticsInsight",
    "QueryType",
    # v2 expanded functions
    "get_financial_data",
    "get_payment_data",
    "get_vendor_spend_data",
    "get_proposal_data",
    "get_expenses_by_tag",
    "compare_periods",
    "forecast_cashflow",
    "get_revenue_by_cohort",
    "get_churn_by_segment",
    "get_team_velocity",
    "get_customer_metrics",
    "get_sales_pipeline",
    "get_infrastructure_costs",
    "get_risk_analysis",
    # v2 query router
    "route_query",
    "generate_generative_ui_stream",
    "QueryIntent",
    "FunctionCall",
    # True generative UI (LLM-powered)
    "generate_true_generative_ui_stream",
    "analyze_query_with_llm",
    "LLMFunctionCall",
    "UIComponent",
    "ANALYTICS_FUNCTIONS",
]
