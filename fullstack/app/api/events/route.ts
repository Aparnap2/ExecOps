import { NextRequest, NextResponse } from "next/server";
import { prisma } from "@/lib/prisma";

export async function POST(req: NextRequest) {
  try {
    const body = await req.json();

    const { source, occurred_at, external_id, payload } = body;

    // Validate required fields
    if (!source || !occurred_at || !payload) {
      return NextResponse.json(
        { error: "Missing required fields: source, occurred_at, payload" },
        { status: 400 }
      );
    }

    // Normalize source to lowercase
    const normalizedSource = source.toLowerCase();

    // Create event
    const event = await prisma.event.create({
      data: {
        source: normalizedSource,
        occurred_at: new Date(occurred_at),
        external_id,
        payload,
      },
    });

    return NextResponse.json({
      id: event.id,
      status: "ok",
    });
  } catch (error) {
    console.error("Event ingestion error:", error);
    return NextResponse.json(
      { error: "Failed to ingest event" },
      { status: 500 }
    );
  }
}

export async function GET(req: NextRequest) {
  try {
    const { searchParams } = new URL(req.url);
    const source = searchParams.get("source");
    const since = searchParams.get("since");
    const limit = parseInt(searchParams.get("limit") || "100");

    const where: any = {};
    if (source) where.source = source;
    if (since) where.occurred_at = { gte: new Date(since) };

    const events = await prisma.event.findMany({
      where,
      orderBy: { occurred_at: "desc" },
      take: limit,
    });

    return NextResponse.json({ events });
  } catch (error) {
    console.error("Fetch events error:", error);
    return NextResponse.json(
      { error: "Failed to fetch events" },
      { status: 500 }
    );
  }
}
