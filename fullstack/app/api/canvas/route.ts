/**
 * Canvas API Route - Direct Analytics Queries
 *
 * REST API for whitelisted analytics functions.
 * NO arbitrary SQL - only predefined queries.
 */

import { NextRequest, NextResponse } from "next/server";
import {
  getRunwayMetrics,
  getBurnRateAnalysis,
  getFailedPaymentsCount,
  getSpendByVendor,
  getRevenueMetrics,
  getProposalStats,
} from "@/lib/analytics";

// Map query parameters to analytics functions
const ANALYTICS_HANDLERS: Record<string, () => Promise<ReturnType<typeof getRunwayMetrics>>> = {
  runway: getRunwayMetrics,
  burn: getBurnRateAnalysis,
  failed_payments: getFailedPaymentsCount,
  vendors: getSpendByVendor,
  revenue: getRevenueMetrics,
  proposals: getProposalStats,
};

// POST /api/canvas - Execute analytics query
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { query } = body;

    if (!query) {
      return NextResponse.json(
        { error: "query is required" },
        { status: 400 }
      );
    }

    // Normalize query
    const normalizedQuery = query.toLowerCase().trim();

    // Match query to handler
    let handlerName = "proposals"; // default
    for (const [key, handler] of Object.entries(ANALYTICS_HANDLERS)) {
      if (normalizedQuery.includes(key) || normalizedQuery.includes(key.replace("_", " "))) {
        handlerName = key;
        break;
      }
    }

    const handler = ANALYTICS_HANDLERS[handlerName];
    const result = await handler();

    return NextResponse.json({
      query,
      matched_handler: handlerName,
      ...result,
    });
  } catch (error) {
    console.error("Canvas API error:", error);
    return NextResponse.json(
      { error: error instanceof Error ? error.message : "Internal server error" },
      { status: 500 }
    );
  }
}

// GET /api/canvas - Health check and available queries
export async function GET() {
  return NextResponse.json({
    status: "healthy",
    service: "canvas-analytics",
    description: "Natural language analytics queries",
    usage: {
      method: "POST",
      body: { query: "string" },
      examples: [
        { query: "What's our runway?" },
        { query: "Show me burn rate" },
        { query: "Failed payments count" },
        { query: "Spend by vendor" },
        { query: "Revenue metrics" },
        { query: "Proposal stats" },
      ],
    },
    available_queries: Object.keys(ANALYTICS_HANDLERS),
  });
}
