/**
 * ActionProposal API Routes
 *
 * CRUD endpoints for ActionProposal management:
 * - GET /api/actions - List all proposals
 * - POST /api/actions - Create new proposal (from webhooks)
 * - GET /api/actions/[id] - Get single proposal
 * - POST /api/actions/[id]/approve - Approve proposal
 * - POST /api/actions/[id]/reject - Reject proposal
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";

// GET /api/actions - List all proposals
export async function GET(req: NextRequest) {
  try {
    const searchParams = req.nextUrl.searchParams;
    const status = searchParams.get("status");
    const vertical = searchParams.get("vertical");
    const limit = parseInt(searchParams.get("limit") || "50");
    const offset = parseInt(searchParams.get("offset") || "0");

    const where: Record<string, unknown> = {};
    if (status) where.status = status;
    if (vertical) where.vertical = vertical;

    const [proposals, total] = await Promise.all([
      prisma.actionProposal.findMany({
        where,
        orderBy: [
          { urgency: "desc" }, // critical, high, medium, low
          { created_at: "desc" },
        ],
        take: limit,
        skip: offset,
      }),
      prisma.actionProposal.count({ where }),
    ]);

    return NextResponse.json({
      proposals,
      pagination: { total, limit, offset },
    });
  } catch (error) {
    console.error("Failed to fetch proposals:", error);
    return NextResponse.json(
      { error: "Failed to fetch proposals" },
      { status: 500 }
    );
  }
}

// POST /api/actions - Create new proposal (triggered by webhooks)
export async function POST(req: NextRequest) {
  try {
    const body = await req.json();
    const { event_type, event_context, urgency } = body;

    // Validate required fields
    if (!event_type) {
      return NextResponse.json(
        { error: "event_type is required" },
        { status: 400 }
      );
    }

    // Route to AI service for processing
    const res = await fetch(`${AI_SERVICE_URL}/process_event`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        event_type,
        event_context: event_context || {},
        urgency: urgency || "low",
      }),
    });

    if (!res.ok) {
      throw new Error(`AI service error: ${res.statusText}`);
    }

    const aiResult = await res.json();

    // Store in database
    const proposal = await prisma.actionProposal.create({
      data: {
        status: "pending",
        urgency: aiResult.urgency || urgency || "low",
        vertical: aiResult.vertical,
        action_type: aiResult.action_type,
        payload: aiResult.payload || {},
        reasoning: aiResult.reasoning,
        context_summary: aiResult.context_summary,
        confidence: aiResult.confidence || 0.8,
        event_id: aiResult.event_id,
      },
    });

    return NextResponse.json({ proposal }, { status: 201 });
  } catch (error) {
    console.error("Failed to create proposal:", error);
    return NextResponse.json(
      { error: "Failed to create proposal" },
      { status: 500 }
    );
  }
}
