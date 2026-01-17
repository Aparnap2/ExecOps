"""Query Router for v2 Generative Analytics.

This module provides intelligent query routing using LLM to determine
which analytics functions to call based on natural language queries.

v2 Feature: True generative UI where LLM decides which functions to call.
"""

import json
import logging
import asyncio
from datetime import datetime
from typing import AsyncGenerator, Any, TypedDict
from enum import Enum

from .generator import (
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

logger = logging.getLogger(__name__)


class FunctionCall(TypedDict):
    """Represents a function call determined by the LLM router."""
    function_name: str
    parameters: dict[str, Any]
    reason: str


class QueryIntent(Enum):
    """Possible query intents for v2 generative UI."""
    RUNWAY = "runway"
    BURN_ANALYSIS = "burn_analysis"
    REVENUE = "revenue"
    EXPENSES = "expenses"
    PAYMENTS = "payments"
    PROPOSALS = "proposals"
    COMPARISON = "comparison"
    FORECAST = "forecast"
    COHORT = "cohort"
    CHURN = "churn"
    TEAM = "team"
    CUSTOMERS = "customers"
    SALES = "sales"
    INFRASTRUCTURE = "infrastructure"
    RISK = "risk"
    GENERAL = "general"


# Function registry for LLM routing
FUNCTION_REGISTRY = {
    "get_financial_data": {
        "description": "Get core financial metrics (cash, burn, revenue, MRR)",
        "triggers": ["cash", "money", "financial", "bank"],
    },
    "get_expenses_by_tag": {
        "description": "Get expenses grouped by tag/category (infrastructure, marketing, etc.)",
        "triggers": ["expense", "spend by", "breakdown", "category"],
        "params": {"tag": "optional tag filter"},
    },
    "compare_periods": {
        "description": "Compare metrics across time periods (MoM, QoQ, YoY)",
        "triggers": ["compare", "vs ", "versus", "change", "growth", "period"],
        "params": {"metric": "what to compare", "periods": "time periods"},
    },
    "forecast_cashflow": {
        "description": "Project future cash position and runway",
        "triggers": ["forecast", "projection", "future cash", "runway projection"],
        "params": {"months": "projection horizon"},
    },
    "get_revenue_by_cohort": {
        "description": "Revenue breakdown by customer cohort",
        "triggers": ["cohort", "quarterly", "by customer", "arr by"],
    },
    "get_churn_by_segment": {
        "description": "Churn analysis by customer segment (enterprise, starter, etc.)",
        "triggers": ["churn", "attrition", "cancellation", "by segment"],
    },
    "get_team_velocity": {
        "description": "Engineering team productivity metrics",
        "triggers": ["team", "engineering", "velocity", "commits", "pr", "deploy"],
    },
    "get_customer_metrics": {
        "description": "Customer acquisition and retention (CAC, LTV, retention)",
        "triggers": ["customer", "cac", "ltv", "acquisition", "retention"],
    },
    "get_sales_pipeline": {
        "description": "Sales pipeline and forecast",
        "triggers": ["sales", "pipeline", "deals", "forecast", "revenue forecast"],
    },
    "get_infrastructure_costs": {
        "description": "Cloud and infrastructure cost breakdown",
        "triggers": ["infrastructure", "cloud", "aws", "cost", "infra"],
    },
    "get_risk_analysis": {
        "description": "Comprehensive risk assessment",
        "triggers": ["risk", "overall health", "alerts", "status"],
    },
    "get_vendor_spend_data": {
        "description": "Vendor spending breakdown",
        "triggers": ["vendor", "supplier", "monthly spend"],
    },
    "get_proposal_data": {
        "description": "Action proposal statistics",
        "triggers": ["proposal", "action", "pending"],
    },
}


async def route_query(query: str) -> list[FunctionCall]:
    """
    Route a natural language query to the appropriate analytics functions.

    This uses simple keyword-based routing. In production, this would use
    an LLM to intelligently determine which functions to call.

    Args:
        query: Natural language query from user

    Returns:
        List of function calls to execute
    """
    query_lower = query.lower()
    function_calls: list[FunctionCall] = []

    # Determine primary intent and add relevant functions
    if any(w in query_lower for w in ["runway", "cash", "money", "bank"]):
        function_calls.append(FunctionCall(
            function_name="forecast_cashflow",
            parameters={"months": 12},
            reason="User asked about runway/cash position",
        ))

    if any(w in query_lower for w in ["burn", "spend", "expense", "cost"]):
        function_calls.append(FunctionCall(
            function_name="get_expenses_by_tag",
            parameters={},
            reason="User asked about burn/expenses",
        ))

    if any(w in query_lower for w in ["revenue", "mrr", "arr", "sales"]):
        function_calls.append(FunctionCall(
            function_name="get_customer_metrics",
            parameters={},
            reason="User asked about revenue/customers",
        ))
        function_calls.append(FunctionCall(
            function_name="get_sales_pipeline",
            parameters={},
            reason="User asked about sales pipeline",
        ))

    if any(w in query_lower for w in ["compare", "vs", "versus", "change", "growth"]):
        # Extract what to compare
        metric = "revenue"
        if "burn" in query_lower or "spend" in query_lower:
            metric = "burn"
        elif "customer" in query_lower:
            metric = "customers"
        function_calls.append(FunctionCall(
            function_name="compare_periods",
            parameters={"metric": metric},
            reason=f"User wants to compare {metric}",
        ))

    if any(w in query_lower for w in ["churn", "attrition", "cancel"]):
        function_calls.append(FunctionCall(
            function_name="get_churn_by_segment",
            parameters={},
            reason="User asked about churn",
        ))

    if any(w in query_lower for w in ["team", "engineering", "velocity", "deploy"]):
        function_calls.append(FunctionCall(
            function_name="get_team_velocity",
            parameters={},
            reason="User asked about team/engineering metrics",
        ))

    if any(w in query_lower for w in ["customer", "cac", "ltv", "acquisition", "retention"]):
        function_calls.append(FunctionCall(
            function_name="get_customer_metrics",
            parameters={},
            reason="User asked about customer metrics",
        ))

    if any(w in query_lower for w in ["infrastructure", "cloud", "aws", "infra"]):
        function_calls.append(FunctionCall(
            function_name="get_infrastructure_costs",
            parameters={},
            reason="User asked about infrastructure costs",
        ))

    if any(w in query_lower for w in ["risk", "health", "alert", "status", "overall"]):
        function_calls.append(FunctionCall(
            function_name="get_risk_analysis",
            parameters={},
            reason="User asked about overall risk/health",
        ))

    if any(w in query_lower for w in ["forecast", "projection", "future"]):
        function_calls.append(FunctionCall(
            function_name="forecast_cashflow",
            parameters={"months": 6},
            reason="User wants a forecast/projection",
        ))

    if any(w in query_lower for w in ["cohort", "quarterly"]):
        function_calls.append(FunctionCall(
            function_name="get_revenue_by_cohort",
            parameters={},
            reason="User asked about cohort analysis",
        ))

    if any(w in query_lower for w in ["proposal", "action", "pending"]):
        function_calls.append(FunctionCall(
            function_name="get_proposal_data",
            parameters={},
            reason="User asked about proposals",
        ))

    # Default: always include financial summary
    if not function_calls:
        function_calls.append(FunctionCall(
            function_name="get_financial_data",
            parameters={},
            reason="Default: user query didn't match specific functions",
        ))
        function_calls.append(FunctionCall(
            function_name="get_risk_analysis",
            parameters={},
            reason="Default: include overall health summary",
        ))

    return function_calls


async def execute_function_call(call: FunctionCall) -> dict:
    """Execute a function call from the router."""
    func_name = call["function_name"]
    params = call["parameters"]

    function_map = {
        "get_financial_data": get_financial_data,
        "get_expenses_by_tag": lambda: get_expenses_by_tag(params.get("tag")),
        "compare_periods": lambda: compare_periods(params.get("metric", "revenue"), params.get("periods")),
        "forecast_cashflow": lambda: forecast_cashflow(params.get("months", 6)),
        "get_revenue_by_cohort": lambda: get_revenue_by_cohort(),
        "get_churn_by_segment": lambda: get_churn_by_segment(),
        "get_team_velocity": get_team_velocity,
        "get_customer_metrics": get_customer_metrics,
        "get_sales_pipeline": get_sales_pipeline,
        "get_infrastructure_costs": get_infrastructure_costs,
        "get_risk_analysis": get_risk_analysis,
        "get_vendor_spend_data": get_vendor_spend_data,
        "get_proposal_data": get_proposal_data,
    }

    if func_name in function_map:
        func = function_map[func_name]
        logger.debug(f"Executing function: {func_name}, func type: {type(func)}")
        result = await func()
        logger.debug(f"Function result type: {type(result)}")
        return {
            "function": func_name,
            "data": result,
            "reason": call["reason"],
        }
    else:
        return {
            "function": func_name,
            "error": "Unknown function",
            "reason": call["reason"],
        }


async def generate_generative_ui_stream(query: str) -> AsyncGenerator[dict, None]:
    """
    Generate v2 generative UI - LLM determines which functions to call.

    This is the main entry point for v2 generative analytics.
    The LLM (or rule-based router) decides what functions to call,
    and results are composed into dynamic UI components.

    Args:
        query: Natural language query

    Yields:
        Streaming updates including:
        - thinking: LLM is analyzing
        - routing: Function routing decision
        - function_call: Executing a function
        - data: Function result
        - complete: Final composed result with UI hints
    """
    query_lower = query.lower()

    # Step 1: Thinking/analyzing
    yield {
        "type": "thinking",
        "message": f"Analyzing your query: \"{query}\"",
        "timestamp": datetime.utcnow().isoformat(),
    }

    await asyncio.sleep(0.1)  # Small delay for streaming effect

    # Step 2: Route query to functions
    function_calls = await route_query(query)

    yield {
        "type": "routing",
        "query": query,
        "function_calls": [
            {"name": f["function_name"], "reason": f["reason"]}
            for f in function_calls
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Step 3: Execute each function and stream results
    all_results = {}
    ui_components = []

    for i, call in enumerate(function_calls):
        yield {
            "type": "function_call",
            "function": call["function_name"],
            "progress": f"{i + 1}/{len(function_calls)}",
            "timestamp": datetime.utcnow().isoformat(),
        }

        result = await execute_function_call(call)
        all_results[call["function_name"]] = result["data"]

        # Determine UI components based on data shape
        component_hint = determine_ui_component(result["data"])
        ui_components.append({
            "function": call["function_name"],
            "component": component_hint,
        })

        yield {
            "type": "data",
            "function": call["function_name"],
            "data": result["data"],
            "component_hint": component_hint,
            "timestamp": datetime.utcnow().isoformat(),
        }

        await asyncio.sleep(0.1)

    # Step 4: Compose final result with UI instructions
    composed_result = compose_ui_result(query, all_results, ui_components)

    yield {
        "type": "complete",
        "query": query,
        "results": all_results,
        "ui_components": ui_components,
        "composed": composed_result,
        "timestamp": datetime.utcnow().isoformat(),
    }


def determine_ui_component(data: dict) -> str:
    """Determine which UI component to render based on data shape."""
    if "by_tag" in data or "by_vendor" in data:
        return "bar_chart"
    if "by_segment" in data or "by_category" in data:
        return "donut_chart"
    if "projection" in data:
        return "sparkline"
    if "data" in data and "changes" in data:
        return "comparison_table"
    if "overall_score" in data or "status" in data:
        return "metric_card"
    if "by_cohort" in data:
        return "data_table"
    if "velocity" in data or "commit_activity" in data:
        return "metrics_grid"
    return "metric_card"


def compose_ui_result(query: str, results: dict, components: list) -> dict:
    """Compose the final UI result with component instructions."""
    return {
        "query": query,
        "component_instructions": [
            {
                "component": c["component"],
                "data": results.get(c["function"], {}),
                "config": get_component_config(c["component"], results.get(c["function"], {})),
            }
            for c in components
        ],
        "suggested_questions": generate_suggestions(results),
    }


def get_component_config(component_type: str, data: dict) -> dict:
    """Get configuration for a specific UI component."""
    configs = {
        "bar_chart": {
            "height": 300,
            "showLegend": True,
            "valueFormat": "${:,.0f}",
        },
        "donut_chart": {
            "height": 250,
            "showLegend": True,
            "innerRadius": 60,
        },
        "sparkline": {
            "height": 80,
            "showPoints": False,
            "animate": True,
        },
        "data_table": {
            "sortable": True,
            "pageSize": 10,
        },
        "metrics_grid": {
            "columns": 3,
            "showTrends": True,
        },
        "metric_card": {
            "showTrend": True,
            "trendFormat": "{value}{direction}",
        },
    }
    return configs.get(component_type, {})


def generate_suggestions(results: dict) -> list[str]:
    """Generate follow-up questions based on results."""
    suggestions = []

    if "get_financial_data" in results or "forecast_cashflow" in results:
        suggestions.append("What's our burn rate trend?")
        suggestions.append("Show me revenue breakdown")

    if "get_churn_by_segment" in results:
        suggestions.append("Which customers are at risk?")
        suggestions.append("What are top churn reasons?")

    if "get_team_velocity" in results:
        suggestions.append("How's our deployment frequency?")
        suggestions.append("Show PR review times")

    if "get_infrastructure_costs" in results:
        suggestions.append("Where can we optimize costs?")
        suggestions.append("What's driving AWS costs?")

    if "get_risk_analysis" in results:
        suggestions.append("What are the main risks?")
        suggestions.append("Show technical debt details")

    return suggestions[:4]  # Limit to 4 suggestions
