/**
 * Whitelisted Analytics Module
 *
 * Safe, predefined analytics queries for the Canvas feature.
 * NO arbitrary SQL - only these whitelisted functions may be called.
 *
 * Each function:
 * - Has a unique name for NL routing
 * - Returns typed results
 * - Is safe to expose to users
 */

import { prisma } from "./prisma";

// =============================================================================
// Analytics Function Types
// =============================================================================

export interface AnalyticsResult<T = unknown> {
  data: T;
  cached: boolean;
  generated_at: string;
}

export type AnalyticsFunction<T = unknown> = () => Promise<AnalyticsResult<T>>;

// =============================================================================
// Whitelisted Analytics Functions
// =============================================================================

// Type helpers for Prisma Json fields
type JsonPayload = Record<string, unknown>;

function isJsonObject(payload: unknown): payload is JsonPayload {
  return typeof payload === "object" && payload !== null && !Array.isArray(payload);
}

function getPayloadType(payload: unknown): string | undefined {
  return isJsonObject(payload) ? (payload.type as string | undefined) : undefined;
}

function getPayloadAmount(payload: unknown): number {
  return isJsonObject(payload) ? Number(payload.amount || 0) : 0;
}

function getPayloadAvailable(payload: unknown): number {
  return isJsonObject(payload) ? Number(payload.available || 0) : 0;
}

function getPayloadString(payload: unknown, key: string): string {
  return isJsonObject(payload) ? (payload[key] as string) || "" : "";
}

/**
 * Runway Calculation
 * Calculates months of runway based on current cash and burn rate
 */
export async function getRunwayMetrics(): Promise<AnalyticsResult<{
  current_cash: number;
  monthly_burn: number;
  runway_months: number;
  trend: "stable" | "improving" | "declining";
}>> {
  // Get total cash from recent balance events
  const cashEvents = await prisma.event.findMany({
    where: {
      source_type: { contains: "stripe" },
      processed: true,
    },
    orderBy: { created_at: "desc" },
    take: 100,
  });

  // Calculate current cash (simplified - from recent balance entries)
  let currentCash = 0;
  const latestBalance = cashEvents.find(e => getPayloadType(e.payload) === "balance");
  if (latestBalance) {
    currentCash = getPayloadAvailable(latestBalance.payload);
  }

  // Calculate monthly burn from spending events
  const spendingEvents = await prisma.event.findMany({
    where: {
      source_type: { contains: "stripe" },
      payload: { path: ["type"], equals: "charge" },
    },
    orderBy: { created_at: "desc" },
    take: 500,
  });

  // Average monthly spend (last 30 days of events)
  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const recentSpend = spendingEvents
    .filter(e => new Date(e.created_at) >= thirtyDaysAgo)
    .reduce((sum, e) => sum + getPayloadAmount(e.payload), 0);

  const monthlyBurn = recentSpend / 100; // Convert cents to dollars
  const runwayMonths = monthlyBurn > 0 ? currentCash / monthlyBurn : 999;

  return {
    data: {
      current_cash: currentCash,
      monthly_burn: Math.round(monthlyBurn * 100) / 100,
      runway_months: Math.round(runwayMonths * 10) / 10,
      trend: runwayMonths > 12 ? "stable" : runwayMonths > 6 ? "improving" : "declining",
    },
    cached: false,
    generated_at: new Date().toISOString(),
  };
}

/**
 * Burn Rate Analysis
 * Detailed breakdown of monthly spending
 */
export async function getBurnRateAnalysis(): Promise<AnalyticsResult<{
  total_monthly: number;
  by_category: Record<string, number>;
  top_vendors: { name: string; amount: number }[];
  daily_average: number;
}>> {
  // Get spending events from last 30 days
  const spendingEvents = await prisma.event.findMany({
    where: {
      source_type: { contains: "stripe" },
      payload: { path: ["type"], equals: "charge" },
    },
    orderBy: { created_at: "desc" },
    take: 500,
  });

  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const recentSpend = spendingEvents
    .filter(e => new Date(e.created_at) >= thirtyDaysAgo)
    .map(e => ({
      amount: getPayloadAmount(e.payload) / 100,
      category: getPayloadString(e.payload, "description") || "uncategorized",
      description: getPayloadString(e.payload, "description") || "Unknown",
    }));

  const totalMonthly = recentSpend.reduce((sum, s) => sum + s.amount, 0);

  // Group by description (vendor)
  const vendorSpend: Record<string, number> = {};
  recentSpend.forEach(s => {
    const vendor = s.description?.split(" ")[0] || "unknown";
    vendorSpend[vendor] = (vendorSpend[vendor] || 0) + s.amount;
  });

  const topVendors = Object.entries(vendorSpend)
    .map(([name, amount]) => ({ name, amount: Math.round(amount * 100) / 100 }))
    .sort((a, b) => b.amount - a.amount)
    .slice(0, 5);

  return {
    data: {
      total_monthly: Math.round(totalMonthly * 100) / 100,
      by_category: {}, // Could extend with ML categorization
      top_vendors: topVendors,
      daily_average: Math.round((totalMonthly / 30) * 100) / 100,
    },
    cached: false,
    generated_at: new Date().toISOString(),
  };
}

/**
 * Failed Payments Count
 * Count of failed payment attempts (for churn risk)
 */
export async function getFailedPaymentsCount(): Promise<AnalyticsResult<{
  total_failed: number;
  recent_24h: number;
  recent_7d: number;
  failure_rate: number;
}>> {
  // Get all failed payment events
  const failedEvents = await prisma.event.findMany({
    where: {
      source_type: { contains: "stripe" },
      payload: { path: ["type"], equals: "payment_failed" },
    },
    orderBy: { created_at: "desc" },
  });

  const now = new Date();
  const dayAgo = new Date(now.getTime() - 24 * 60 * 60 * 1000);
  const weekAgo = new Date(now.getTime() - 7 * 24 * 60 * 60 * 1000);

  const recent_24h = failedEvents.filter(e => new Date(e.created_at) >= dayAgo).length;
  const recent_7d = failedEvents.filter(e => new Date(e.created_at) >= weekAgo).length;

  // Get total payment attempts for failure rate
  const allPayments = await prisma.event.findMany({
    where: {
      source_type: { contains: "stripe" },
      OR: [
        { payload: { path: ["type"], equals: "charge" } },
        { payload: { path: ["type"], equals: "payment_failed" } },
      ],
    },
    orderBy: { created_at: "desc" },
    take: 1000,
  });

  const failureRate = allPayments.length > 0
    ? Math.round((failedEvents.length / allPayments.length) * 1000) / 10
    : 0;

  return {
    data: {
      total_failed: failedEvents.length,
      recent_24h,
      recent_7d,
      failure_rate: failureRate,
    },
    cached: false,
    generated_at: new Date().toISOString(),
  };
}

/**
 * Spend by Vendor
 * Aggregated spending per vendor
 */
export async function getSpendByVendor(): Promise<AnalyticsResult<{
  vendors: { name: string; total: number; count: number; last_payment: string }[];
  total_spend: number;
}>> {
  const spendingEvents = await prisma.event.findMany({
    where: {
      source_type: { contains: "stripe" },
      payload: { path: ["type"], equals: "charge" },
    },
    orderBy: { created_at: "desc" },
    take: 500,
  });

  const vendorSpend: Record<string, { total: number; count: number; lastDate: Date }> = {};

  spendingEvents.forEach(e => {
    const description = getPayloadString(e.payload, "description") || "unknown";
    const amount = getPayloadAmount(e.payload) / 100;
    const vendor = description?.split(" ")[0] || "unknown";

    if (!vendorSpend[vendor]) {
      vendorSpend[vendor] = { total: 0, count: 0, lastDate: new Date(e.created_at) };
    }
    vendorSpend[vendor].total += amount;
    vendorSpend[vendor].count += 1;
    if (new Date(e.created_at) > vendorSpend[vendor].lastDate) {
      vendorSpend[vendor].lastDate = new Date(e.created_at);
    }
  });

  const vendors = Object.entries(vendorSpend)
    .map(([name, data]) => ({
      name,
      total: Math.round(data.total * 100) / 100,
      count: data.count,
      last_payment: data.lastDate.toISOString(),
    }))
    .sort((a, b) => b.total - a.total);

  const totalSpend = vendors.reduce((sum, v) => sum + v.total, 0);

  return {
    data: {
      vendors,
      total_spend: Math.round(totalSpend * 100) / 100,
    },
    cached: false,
    generated_at: new Date().toISOString(),
  };
}

/**
 * Revenue Metrics
 * Basic revenue tracking from Stripe invoices
 */
export async function getRevenueMetrics(): Promise<AnalyticsResult<{
  total_revenue: number;
  invoice_count: number;
  avg_invoice_value: number;
  recent_30d: number;
}>> {
  const invoices = await prisma.event.findMany({
    where: {
      source_type: { contains: "stripe" },
      payload: { path: ["type"], equals: "invoice" },
    },
    orderBy: { created_at: "desc" },
    take: 200,
  });

  const thirtyDaysAgo = new Date();
  thirtyDaysAgo.setDate(thirtyDaysAgo.getDate() - 30);

  const recentInvoices = invoices.filter(e => new Date(e.created_at) >= thirtyDaysAgo);

  const totalRevenue = invoices.reduce((sum, e) => sum + (Number(getPayloadString(e.payload, "amount_due")) || 0) / 100, 0);
  const recentRevenue = recentInvoices.reduce((sum, e) => sum + (Number(getPayloadString(e.payload, "amount_due")) || 0) / 100, 0);

  return {
    data: {
      total_revenue: Math.round(totalRevenue * 100) / 100,
      invoice_count: invoices.length,
      avg_invoice_value: invoices.length > 0 ? Math.round((totalRevenue / invoices.length) * 100) / 100 : 0,
      recent_30d: Math.round(recentRevenue * 100) / 100,
    },
    cached: false,
    generated_at: new Date().toISOString(),
  };
}

/**
 * Proposal Stats
 * Summary of ActionProposal activity
 */
export async function getProposalStats(): Promise<AnalyticsResult<{
  total: number;
  pending: number;
  approved: number;
  rejected: number;
  by_vertical: Record<string, number>;
  avg_confidence: number;
}>> {
  const proposals = await prisma.actionProposal.findMany({
    orderBy: { created_at: "desc" },
    take: 500,
  });

  const byVertical: Record<string, number> = {};
  let totalConfidence = 0;

  proposals.forEach(p => {
    byVertical[p.vertical] = (byVertical[p.vertical] || 0) + 1;
    totalConfidence += p.confidence;
  });

  return {
    data: {
      total: proposals.length,
      pending: proposals.filter(p => p.status === "pending" || p.status === "pending_approval").length,
      approved: proposals.filter(p => p.status === "approved" || p.status === "executed").length,
      rejected: proposals.filter(p => p.status === "rejected").length,
      by_vertical: byVertical,
      avg_confidence: proposals.length > 0 ? Math.round((totalConfidence / proposals.length) * 1000) / 1000 : 0,
    },
    cached: false,
    generated_at: new Date().toISOString(),
  };
}

// =============================================================================
// Whitelist Registry (NL → Function mapping)
// =============================================================================

export const WHITELISTED_ANALYTICS: Record<string, AnalyticsFunction> = {
  "runway": getRunwayMetrics,
  "runway calculation": getRunwayMetrics,
  "how much runway do we have": getRunwayMetrics,
  "cash runway": getRunwayMetrics,

  "burn rate": getBurnRateAnalysis,
  "monthly burn": getBurnRateAnalysis,
  "burn rate analysis": getBurnRateAnalysis,
  "spending breakdown": getBurnRateAnalysis,

  "failed payments": getFailedPaymentsCount,
  "failed payment count": getFailedPaymentsCount,
  "payment failures": getFailedPaymentsCount,
  "churn risk": getFailedPaymentsCount,

  "spend by vendor": getSpendByVendor,
  "vendor spend": getSpendByVendor,
  "spending by vendor": getSpendByVendor,
  "expenses by vendor": getSpendByVendor,

  "revenue": getRevenueMetrics,
  "revenue metrics": getRevenueMetrics,
  "total revenue": getRevenueMetrics,
  "invoice summary": getRevenueMetrics,

  "proposal stats": getProposalStats,
  "proposal summary": getProposalStats,
  "action proposal stats": getProposalStats,
};

export type AnalyticsFunctionName = keyof typeof WHITELISTED_ANALYTICS;

// =============================================================================
// NL Query Parser
// =============================================================================

/**
 * Parse natural language query and match to whitelisted function
 */
export function parseAnalyticsQuery(query: string): {
  matched: boolean;
  function_name: string | null;
  confidence: number;
} {
  const normalized = query.toLowerCase().trim();

  // Direct matches with scoring
  const matches: { name: string; score: number }[] = [];

  for (const [pattern, _fn] of Object.entries(WHITELISTED_ANALYTICS)) {
    let score = 0;

    // Exact phrase match
    if (normalized === pattern) {
      score = 100;
    }
    // Contains pattern
    else if (normalized.includes(pattern)) {
      score = pattern.length / normalized.length;
    }
    // Word overlap
    else {
      const queryWords = normalized.split(/\s+/);
      const patternWords = pattern.split(/\s+/);
      const overlap = queryWords.filter(w => patternWords.some(pw => w === pw || pw.includes(w))).length;
      score = overlap / Math.max(queryWords.length, patternWords.length);
    }

    if (score > 0.3) {
      matches.push({ name: pattern, score });
    }
  }

  if (matches.length === 0) {
    return { matched: false, function_name: null, confidence: 0 };
  }

  // Sort by score and return best match
  matches.sort((a, b) => b.score - a.score);
  const best = matches[0];

  return {
    matched: best.score > 0.3,
    function_name: best.name,
    confidence: Math.round(best.score * 100) / 100,
  };
}
