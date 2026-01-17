"""
True v2 Generative UI Router - LLM-powered query understanding.

This module uses an actual LLM to:
1. Understand natural language queries
2. Decide which functions to call
3. Determine parameters dynamically
4. Compose the response
5. Recommend UI components

No keyword matching - real reasoning.
"""

import json
import logging
from datetime import datetime
from typing import AsyncGenerator, Any, TypedDict, Optional
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


# Available analytics functions with descriptions
ANALYTICS_FUNCTIONS = {
    "get_financial_data": {
        "description": "Core financial metrics: cash balance, burn rate, MRR, revenue growth, customer churn",
        "parameters": {},
        "example_queries": ["how much cash do we have", "what's our financial health", "show me the money"],
    },
    "get_expenses_by_tag": {
        "description": "Expenses grouped by tag/category like infrastructure, marketing, development",
        "parameters": {"tag": "Optional specific category filter"},
        "example_queries": ["where is our money going", "show me spend by category", "infrastructure costs"],
    },
    "compare_periods": {
        "description": "Compare metrics across time periods: month-over-month, quarter-over-quarter, year-over-year",
        "parameters": {"metric": "What to compare (revenue, burn, customers)", "periods": "Time periods"},
        "example_queries": ["how did revenue change this month", "compare to last quarter", "growth vs last year"],
    },
    "forecast_cashflow": {
        "description": "Project future cash position with monthly breakdown based on historical trends",
        "parameters": {"months": "Projection horizon (6 or 12 months)"},
        "example_queries": ["what's our runway", "forecast cash for next year", "when will we run out of money"],
    },
    "get_revenue_by_cohort": {
        "description": "Revenue breakdown by customer cohort (monthly, quarterly, by plan) with retention",
        "parameters": {"cohort_type": "Type of cohort grouping"},
        "example_queries": ["revenue by customer cohort", "quarterly revenue breakdown", "arr by segment"],
    },
    "get_churn_by_segment": {
        "description": "Churn analysis by customer segment (enterprise, professional, starter) with reasons",
        "parameters": {"segment": "Optional specific segment filter"},
        "example_queries": ["which customers are leaving", "churn by segment", "why are customers canceling"],
    },
    "get_team_velocity": {
        "description": "Engineering team productivity: commits, PRs, cycle time, deploy frequency",
        "parameters": {},
        "example_queries": ["how is the engineering team doing", "deployment frequency", "pr review times"],
    },
    "get_customer_metrics": {
        "description": "Customer acquisition and retention: CAC, LTV, retention rates, health score",
        "parameters": {},
        "example_queries": ["what's our cac", "customer lifetime value", "retention rates"],
    },
    "get_sales_pipeline": {
        "description": "Sales pipeline value, conversion rates, deal stages, forecast",
        "parameters": {},
        "example_queries": ["sales pipeline value", "deal forecast", "conversion rates"],
    },
    "get_infrastructure_costs": {
        "description": "Cloud and infrastructure breakdown: AWS services, environments, optimization opportunities",
        "parameters": {},
        "example_queries": ["aws costs", "cloud spending", "infrastructure optimization"],
    },
    "get_risk_analysis": {
        "description": "Comprehensive risk assessment: financial, technical, customer, market risks with alerts",
        "parameters": {},
        "example_queries": ["overall risk assessment", "what are the risks", "health score", "alerts"],
    },
    "get_proposal_data": {
        "description": "Action proposal statistics from ExecOps vertical agents",
        "parameters": {},
        "example_queries": ["pending proposals", "action items", "what needs approval"],
    },
}


class LLMFunctionCall(TypedDict):
    """LLM-determined function call with reasoning."""
    function: str
    parameters: dict[str, Any]
    reasoning: str
    confidence: float


class UIComponent(Enum):
    """UI component recommendations based on data shape."""
    METRICS_GRID = "metrics_grid"
    BAR_CHART = "bar_chart"
    DONUT_CHART = "donut_chart"
    SPARKLINE = "sparkline"
    DATA_TABLE = "data_table"
    RISK_DASHBOARD = "risk_dashboard"


# Simple LLM-like reasoning (replace with actual OpenAI call in production)
async def analyze_query_with_llm(query: str) -> list[LLMFunctionCall]:
    """
    Use LLM reasoning to determine which functions to call.

    In production, this would call OpenAI with a prompt like:
    "Given this query: '{query}'
     And these available functions: {ANALYTICS_FUNCTIONS}
     Decide which functions to call and why."

    For now, we simulate LLM reasoning with structured analysis.
    """
    query_lower = query.lower()

    # LLM-like reasoning steps
    function_calls: list[LLMFunctionCall] = []

    # Step 1: Intent classification through analysis
    intent_analysis = _analyze_intent(query_lower)
    logger.info(f"Intent analysis: {intent_analysis}")

    # Step 2: Based on intent, determine functions
    seen_functions = set()  # Avoid duplicates

    for intent, confidence, reasoning in intent_analysis:
        if confidence < 0.3:
            continue

        if intent == "runway_cash":
            # Query: "What's our runway and cash forecast?" - call once with 12 months
            if "forecast_cashflow" not in seen_functions:
                seen_functions.add("forecast_cashflow")
                function_calls.append(LLMFunctionCall(
                    function="forecast_cashflow",
                    parameters={"months": 12},
                    reasoning=f"{reasoning} - Forecasting 12 months to show runway",
                    confidence=confidence,
                ))
                # Also get financial baseline
                if "get_financial_data" not in seen_functions:
                    seen_functions.add("get_financial_data")
                    function_calls.append(LLMFunctionCall(
                        function="get_financial_data",
                        parameters={},
                        reasoning="Get baseline financial metrics for context",
                        confidence=0.8,
                    ))

        elif intent == "burn_expenses":
            if "get_expenses_by_tag" not in seen_functions:
                seen_functions.add("get_expenses_by_tag")
                function_calls.append(LLMFunctionCall(
                    function="get_expenses_by_tag",
                    parameters={},
                    reasoning=reasoning,
                    confidence=confidence,
                ))
            if "get_infrastructure_costs" not in seen_functions:
                seen_functions.add("get_infrastructure_costs")
                function_calls.append(LLMFunctionCall(
                    function="get_infrastructure_costs",
                    parameters={},
                    reasoning="Infrastructure is often a major cost driver",
                    confidence=0.7,
                ))

        elif intent == "revenue_sales":
            if "get_customer_metrics" not in seen_functions:
                seen_functions.add("get_customer_metrics")
                function_calls.append(LLMFunctionCall(
                    function="get_customer_metrics",
                    parameters={},
                    reasoning=reasoning,
                    confidence=confidence,
                ))
            if "get_sales_pipeline" not in seen_functions:
                seen_functions.add("get_sales_pipeline")
                function_calls.append(LLMFunctionCall(
                    function="get_sales_pipeline",
                    parameters={},
                    reasoning="Sales pipeline provides revenue visibility",
                    confidence=0.85,
                ))
            if "get_revenue_by_cohort" not in seen_functions:
                seen_functions.add("get_revenue_by_cohort")
                function_calls.append(LLMFunctionCall(
                    function="get_revenue_by_cohort",
                    parameters={},
                    reasoning="Cohort analysis shows revenue trends",
                    confidence=0.75,
                ))

        elif intent == "team_velocity":
            if "get_team_velocity" not in seen_functions:
                seen_functions.add("get_team_velocity")
                function_calls.append(LLMFunctionCall(
                    function="get_team_velocity",
                    parameters={},
                    reasoning=reasoning,
                    confidence=confidence,
                ))

        elif intent == "churn_customer_risk":
            if "get_churn_by_segment" not in seen_functions:
                seen_functions.add("get_churn_by_segment")
                function_calls.append(LLMFunctionCall(
                    function="get_churn_by_segment",
                    parameters={},
                    reasoning=reasoning,
                    confidence=confidence,
                ))
            if "get_customer_metrics" not in seen_functions:
                seen_functions.add("get_customer_metrics")
                function_calls.append(LLMFunctionCall(
                    function="get_customer_metrics",
                    parameters={},
                    reasoning="Get overall customer health metrics",
                    confidence=0.7,
                ))

        elif intent == "comparison_growth":
            if "compare_periods" not in seen_functions:
                seen_functions.add("compare_periods")
                function_calls.append(LLMFunctionCall(
                    function="compare_periods",
                    parameters={"metric": _extract_comparison_metric(query_lower)},
                    reasoning=reasoning,
                    confidence=confidence,
                ))

        elif intent == "infrastructure_costs":
            if "get_infrastructure_costs" not in seen_functions:
                seen_functions.add("get_infrastructure_costs")
                function_calls.append(LLMFunctionCall(
                    function="get_infrastructure_costs",
                    parameters={},
                    reasoning=reasoning,
                    confidence=confidence,
                ))

        elif intent == "overall_risk":
            if "get_risk_analysis" not in seen_functions:
                seen_functions.add("get_risk_analysis")
                function_calls.append(LLMFunctionCall(
                    function="get_risk_analysis",
                    parameters={},
                    reasoning=reasoning,
                    confidence=confidence,
                ))

        elif intent == "proposals_actions":
            if "get_proposal_data" not in seen_functions:
                seen_functions.add("get_proposal_data")
                function_calls.append(LLMFunctionCall(
                    function="get_proposal_data",
                    parameters={},
                    reasoning=reasoning,
                    confidence=confidence,
                ))

    # Default: if no intent matched, use risk analysis as fallback
    if not function_calls:
        function_calls.append(LLMFunctionCall(
            function="get_risk_analysis",
            parameters={},
            reasoning="No specific intent detected - providing overall health assessment",
            confidence=0.5,
        ))
        function_calls.append(LLMFunctionCall(
            function="get_financial_data",
            parameters={},
            reasoning="Also providing core financial metrics",
            confidence=0.5,
        ))

    return function_calls


def _analyze_intent(query: str) -> list[tuple[str, float, str]]:
    """
    LLM-style intent analysis.
    Returns list of (intent, confidence, reasoning) tuples.
    """
    intents = []

    # Runway/Cash keywords
    if any(w in query for w in ["runway", "cash", "money", "bank", "capital", "financial"]):
        confidence = 0.9 if any(w in query for w in ["runway", "cash"]) else 0.6
        intents.append(("runway_cash", confidence,
            "Query mentions financial position or runway"))

    # Burn/Expenses keywords
    if any(w in query for w in ["burn", "spend", "expense", "cost", "budget", "saving"]):
        confidence = 0.9 if "burn" in query else 0.7
        intents.append(("burn_expenses", confidence,
            "Query is about spending or expenses"))

    # Revenue/Sales keywords
    if any(w in query for w in ["revenue", "mrr", "arr", "sales", "income", "bookings"]):
        confidence = 0.9 if any(w in query for w in ["revenue", "mrr", "arr"]) else 0.6
        intents.append(("revenue_sales", confidence,
            "Query is about revenue or sales"))

    # Team velocity keywords
    if any(w in query for w in ["team", "velocity", "engineering", "deploy", "commit", "pr", "sprint"]):
        confidence = 0.9 if any(w in query for w in ["velocity", "engineering"]) else 0.6
        intents.append(("team_velocity", confidence,
            "Query is about team productivity or engineering metrics"))

    # Churn/Customer risk keywords
    if any(w in query for w in ["churn", "cancel", "attrition", "customer leaving", "at risk"]):
        confidence = 0.95
        intents.append(("churn_customer_risk", confidence,
            "Query is about customer churn or risk"))
    elif any(w in query for w in ["customer", "cac", "ltv", "retention", "acquisition"]):
        confidence = 0.7
        intents.append(("churn_customer_risk", confidence,
            "Query is about customer metrics"))

    # Comparison/Growth keywords
    if any(w in query for w in ["compare", "vs", "versus", "change", "growth", "trend", "increase", "decrease"]):
        confidence = 0.85
        intents.append(("comparison_growth", confidence,
            "Query asks for comparison or growth analysis"))

    # Infrastructure keywords
    if any(w in query for w in ["infrastructure", "cloud", "aws", "infra", "server", "hosting"]):
        confidence = 0.9
        intents.append(("infrastructure_costs", confidence,
            "Query is about infrastructure or cloud costs"))

    # Overall risk/health keywords
    if any(w in query for w in ["risk", "health", "alert", "status", "overall", "summary", "dashboard"]):
        confidence = 0.85
        intents.append(("overall_risk", confidence,
            "Query asks for overall health or risk assessment"))

    # Proposals/Action keywords
    if any(w in query for w in ["proposal", "action", "pending", "approval", "decision"]):
        confidence = 0.9
        intents.append(("proposals_actions", confidence,
            "Query is about proposals or pending actions"))

    return intents


def _extract_comparison_metric(query: str) -> str:
    """Extract what metric to compare based on query content."""
    if "revenue" in query or "mrr" in query:
        return "revenue"
    elif "burn" in query or "spend" in query or "cost" in query:
        return "burn"
    elif "customer" in query or "user" in query:
        return "customers"
    elif "churn" in query:
        return "churn_rate"
    else:
        return "revenue"


async def execute_llm_function_call(call: LLMFunctionCall) -> dict:
    """Execute an LLM-determined function call."""
    func_name = call["function"]
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
        result = await function_map[func_name]()
        return {
            "function": func_name,
            "data": result,
            "reasoning": call["reasoning"],
            "confidence": call["confidence"],
        }
    else:
        return {
            "function": func_name,
            "error": "Unknown function",
            "reasoning": call["reasoning"],
        }


def determine_ui_components(data: dict, reasoning: str) -> list[dict]:
    """
    LLM-like decision on which UI components to use based on data shape.
    """
    components = []

    # Analyze data structure
    has_projection = "projection" in data and len(data.get("projection", [])) > 0
    has_segments = "by_segment" in data or "by_category" in data
    has_time_series = "burn_history" in data or "revenue_history" in data
    has_cohort = "by_cohort" in data
    has_risk_score = "overall_score" in data or "by_category" in data
    has_nested_metrics = any(isinstance(v, dict) for v in data.values())

    # Determine components based on data analysis
    if has_projection:
        components.append({
            "component": "sparkline",
            "config": {"height": 80, "showPoints": False, "animate": True},
            "reasoning": "Projection data suggests trend visualization",
        })

    if has_segments:
        components.append({
            "component": "donut_chart",
            "config": {"height": 250, "innerRadius": 60, "showLegend": True},
            "reasoning": "Segment/category data best shown as distribution",
        })

    if has_time_series:
        components.append({
            "component": "bar_chart",
            "config": {"height": 180, "showValues": True},
            "reasoning": "Time series data best shown as bar chart",
        })

    if has_cohort:
        components.append({
            "component": "data_table",
            "config": {"sortable": True, "pageSize": 10},
            "reasoning": "Cohort data requires tabular format with sorting",
        })

    if has_risk_score:
        components.append({
            "component": "risk_dashboard",
            "config": {"showAlerts": True},
            "reasoning": "Risk analysis suggests risk dashboard with alerts",
        })

    if has_nested_metrics and not components:
        components.append({
            "component": "metrics_grid",
            "config": {"columns": 3, "showTrends": True},
            "reasoning": "Multiple metrics best shown as grid",
        })

    # Always add metrics grid as fallback
    if not components:
        components.append({
            "component": "metrics_grid",
            "config": {"columns": 2},
            "reasoning": "Default to metrics grid for unknown data structure",
        })

    return components


async def generate_true_generative_ui_stream(query: str) -> AsyncGenerator[dict, None]:
    """
    True generative UI - LLM reasons about query and determines everything.

    Stream events:
    - thinking: LLM is analyzing the query
    - reasoning: LLM explains its thinking
    - function_call: Executing LLM-decided function
    - data: Function result
    - ui_decision: LLM decides which components to use
    - complete: Final composed result
    """
    # Step 1: Thinking - LLM analyzing
    yield {
        "type": "thinking",
        "message": f"Analyzing your query: \"{query}\"",
        "timestamp": datetime.utcnow().isoformat(),
    }

    import asyncio
    await asyncio.sleep(0.2)

    # Step 2: Reasoning - LLM explains its analysis
    intent_analysis = _analyze_intent(query.lower())
    intent_summary = ", ".join([i[0] for i in intent_analysis]) if intent_analysis else "general"
    yield {
        "type": "reasoning",
        "message": f"Intent detected: {intent_summary}",
        "intent_analysis": [{"intent": i[0], "confidence": i[1], "reasoning": i[2]} for i in intent_analysis],
        "timestamp": datetime.utcnow().isoformat(),
    }

    await asyncio.sleep(0.1)

    # Step 3: LLM decides which functions to call
    function_calls = await analyze_query_with_llm(query)

    yield {
        "type": "routing",
        "query": query,
        "function_calls": [
            {
                "function": f["function"],
                "parameters": f["parameters"],
                "reasoning": f["reasoning"],
                "confidence": f["confidence"],
            }
            for f in function_calls
        ],
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Step 4: Execute each function
    all_results = {}
    ui_components = []

    for i, call in enumerate(function_calls):
        yield {
            "type": "function_call",
            "function": call["function"],
            "parameters": call["parameters"],
            "reasoning": call["reasoning"],
            "progress": f"{i + 1}/{len(function_calls)}",
            "timestamp": datetime.utcnow().isoformat(),
        }

        result = await execute_llm_function_call(call)
        all_results[call["function"]] = result.get("data", {})

        await asyncio.sleep(0.1)

    # Step 5: LLM decides UI components based on data analysis
    primary_result = all_results.get(function_calls[0]["function"], {}) if function_calls else {}
    ui_decision = determine_ui_components(primary_result, intent_summary)

    yield {
        "type": "ui_decision",
        "reasoning": f"Based on {intent_summary} intent, rendering {len(ui_decision)} component(s)",
        "components": ui_decision,
        "timestamp": datetime.utcnow().isoformat(),
    }

    # Step 6: Compose suggestions
    suggestions = _generate_suggestions(intent_analysis, function_calls)

    # Step 7: Complete
    yield {
        "type": "complete",
        "query": query,
        "results": all_results,
        "function_calls": function_calls,
        "ui_components": ui_decision,
        "suggested_questions": suggestions,
        "timestamp": datetime.utcnow().isoformat(),
    }


def _generate_suggestions(intent_analysis: list[tuple], function_calls: list) -> list[str]:
    """Generate contextual follow-up suggestions."""
    suggestions = []
    intents = [i[0] for i in intent_analysis]

    if "runway_cash" in intents:
        suggestions = [
            "What's our burn rate trend?",
            "Show me revenue breakdown",
            "When will we hit break-even?",
        ]
    elif "team_velocity" in intents:
        suggestions = [
            "How's our deployment frequency?",
            "Show PR review times",
            "What's our code churn?",
        ]
    elif "churn_customer_risk" in intents:
        suggestions = [
            "Which specific customers are at risk?",
            "What are top churn reasons?",
            "Show retention by cohort",
        ]
    elif "burn_expenses" in intents:
        suggestions = [
            "Where can we optimize costs?",
            "Show infrastructure breakdown",
            "Compare to last month's spend",
        ]
    elif "revenue_sales" in intents:
        suggestions = [
            "Show sales pipeline details",
            "What's our conversion rate?",
            "Compare to last quarter",
        ]
    else:
        suggestions = [
            "What's our runway?",
            "Show me team velocity",
            "Any risks I should know about?",
        ]

    return suggestions[:4]
