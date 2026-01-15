/**
 * ActionProposal Individual Routes
 *
 * Handles individual proposal operations:
 * - GET /api/actions/[id] - Get single proposal
 * - POST /api/actions/[id]/approve - Approve proposal
 * - POST /api/actions/[id]/reject - Reject proposal
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

const AI_SERVICE_URL = process.env.AI_SERVICE_URL || "http://localhost:8000";

// GET /api/actions/[id]
export async function GET(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const proposal = await prisma.actionProposal.findUnique({
      where: { id },
    });

    if (!proposal) {
      return NextResponse.json(
        { error: "Proposal not found" },
        { status: 404 }
      );
    }

    return NextResponse.json({ proposal });
  } catch (error) {
    console.error("Failed to fetch proposal:", error);
    return NextResponse.json(
      { error: "Failed to fetch proposal" },
      { status: 500 }
    );
  }
}

// POST /api/actions/[id]/approve
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await req.json().catch(() => ({}));
    const { approver_id } = body;

    // Get the proposal
    const proposal = await prisma.actionProposal.findUnique({
      where: { id },
    });

    if (!proposal) {
      return NextResponse.json(
        { error: "Proposal not found" },
        { status: 404 }
      );
    }

    if (proposal.status !== "pending" && proposal.status !== "pending_approval") {
      return NextResponse.json(
        { error: `Cannot approve proposal in status: ${proposal.status}` },
        { status: 400 }
      );
    }

    // Update status
    const updated = await prisma.actionProposal.update({
      where: { id },
      data: {
        status: "approved",
        approved_at: new Date().toISOString(),
        approver_id: approver_id || "founder",
      },
    });

    // Execute the action if it's auto-executable
    if (proposal.action_type === "email" || proposal.action_type === "webhook") {
      try {
        await fetch(`${AI_SERVICE_URL}/execute_action`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            proposal_id: id,
            action_type: proposal.action_type,
            payload: proposal.payload,
          }),
        });
      } catch (execError) {
        console.error("Failed to execute action:", execError);
        // Don't fail the approval, just log it
      }
    }

    return NextResponse.json({ proposal: updated });
  } catch (error) {
    console.error("Failed to approve proposal:", error);
    return NextResponse.json(
      { error: "Failed to approve proposal" },
      { status: 500 }
    );
  }
}
