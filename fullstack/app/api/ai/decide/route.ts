import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const { objective, events, constraints } = body;

    // Build decision request
    const decisionReq = {
      request_id: crypto.randomUUID(),
      objective,
      events: events.map((e: any) => ({
        ...e,
        occurred_at: new Date(e.occurred_at).toISOString(),
        source: e.source.toLowerCase(),
      })),
      constraints: constraints || {},
    };

    // Call AI service
    const res = await fetch(`${AI_SERVICE_URL}/decide`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(decisionReq),
    });

    if (!res.ok) {
      throw new Error(`AI service error: ${res.statusText}`);
    }

    const decisionRes = await res.json();

    // Store decision in database
    const decision = await prisma.decision.create({
      data: {
        request_id: decisionReq.request_id,
        objective: decisionReq.objective,
        state: decisionRes.state,
        summary: decisionRes.summary,
        confidence: decisionRes.confidence,
        confidence_breakdown: decisionRes.confidence_breakdown,
        recommendations: decisionRes.recommendations,
        escalations: decisionRes.escalations,
        executed_sops: decisionRes.executed_sops,
      },
    });

    // Store escalations if any
    if (decisionRes.escalations && decisionRes.escalations.length > 0) {
      await prisma.escalation.createMany({
        data: decisionRes.escalations.map((e: any) => ({
          decision_id: decision.id,
          reason: e.reason,
          severity: e.severity,
          context: e.context,
        })),
      });
    }

    return NextResponse.json({
      decision_id: decision.id,
      ...decisionRes,
    });
  } catch (error) {
    console.error("Decision error:", error);
    return NextResponse.json(
      { error: "Failed to process decision" },
      { status: 500 }
    );
  }
}

export async function GET() {
  try {
    const decisions = await prisma.decision.findMany({
      orderBy: { created_at: "desc" },
      take: 50,
    });

    return NextResponse.json({ decisions });
  } catch (error) {
    console.error("Fetch decisions error:", error);
    return NextResponse.json(
      { error: "Failed to fetch decisions" },
      { status: 500 }
    );
  }
}
