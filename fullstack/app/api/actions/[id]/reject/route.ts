/**
 * ActionProposal Reject Route
 *
 * POST /api/actions/[id]/reject
 */

import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

// POST /api/actions/[id]/reject
export async function POST(
  req: NextRequest,
  { params }: { params: Promise<{ id: string }> }
) {
  try {
    const { id } = await params;
    const body = await req.json();
    const { rejection_reason, approver_id } = body;

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
        { error: `Cannot reject proposal in status: ${proposal.status}` },
        { status: 400 }
      );
    }

    // Update status
    const updated = await prisma.actionProposal.update({
      where: { id },
      data: {
        status: "rejected",
        rejection_reason: rejection_reason || "No reason provided",
        approver_id: approver_id || "founder",
      },
    });

    return NextResponse.json({ proposal: updated });
  } catch (error) {
    console.error("Failed to reject proposal:", error);
    return NextResponse.json(
      { error: "Failed to reject proposal" },
      { status: 500 }
    );
  }
}
