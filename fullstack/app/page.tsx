"use client";

import { useState, useEffect } from "react";
import type { ActionProposal } from "@/lib/types";

interface ServiceStatus {
  ai: boolean;
  database: boolean;
}

function StatusBadge({ active }: { active: boolean }) {
  return (
    <span
      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
        active
          ? "bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300"
          : "bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300"
      }`}
    >
      {active ? "Connected" : "Disconnected"}
    </span>
  );
}

function ProposalCard({ proposal }: { proposal: ActionProposal }) {
  const urgencyColors = {
    low: "border-l-zinc-400",
    medium: "border-l-blue-500",
    high: "border-l-orange-500",
    critical: "border-l-red-500",
  };

  const statusColors = {
    pending: "bg-yellow-100 text-yellow-800",
    pending_approval: "bg-yellow-100 text-yellow-800",
    approved: "bg-green-100 text-green-800",
    rejected: "bg-red-100 text-red-800",
    executed: "bg-blue-100 text-blue-800",
  };

  return (
    <div
      className={`p-4 bg-white dark:bg-zinc-900 rounded-lg shadow border-l-4 ${urgencyColors[proposal.urgency]}`}
    >
      <div className="flex justify-between items-start">
        <div>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {proposal.vertical.replace("_", " ")}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
            {new Date(proposal.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex gap-2">
          <span
            className={`px-2 py-1 text-xs font-semibold rounded ${statusColors[proposal.status]}`}
          >
            {proposal.status}
          </span>
          <span
            className={`px-2 py-1 text-xs font-semibold rounded ${
              proposal.urgency === "critical"
                ? "bg-red-100 text-red-800"
                : proposal.urgency === "high"
                ? "bg-orange-100 text-orange-800"
                : "bg-zinc-100 text-zinc-800"
            }`}
          >
            {proposal.urgency}
          </span>
        </div>
      </div>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300 line-clamp-2">
        {proposal.context_summary || proposal.reasoning}
      </p>
      <div className="mt-3 flex items-center justify-between">
        <p className="text-xs text-zinc-500">
          Confidence: {(proposal.confidence * 100).toFixed(0)}%
        </p>
        {proposal.status === "pending" && (
          <div className="flex gap-2">
            <button className="px-3 py-1 text-xs bg-green-600 text-white rounded hover:bg-green-700">
              Approve
            </button>
            <button className="px-3 py-1 text-xs bg-red-600 text-white rounded hover:bg-red-700">
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

export default function Home() {
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>({
    ai: false,
    database: false,
  });
  const [proposals, setProposals] = useState<ActionProposal[]>([]);
  const [loading, setLoading] = useState(true);

  // Fetch service status and proposals
  useEffect(() => {
    async function fetchStatus() {
      try {
        // Check AI service
        try {
          const aiRes = await fetch("http://localhost:8000/health");
          setServiceStatus((prev) => ({ ...prev, ai: aiRes.ok }));
        } catch {
          setServiceStatus((prev) => ({ ...prev, ai: false }));
        }

        // Check database via API
        try {
          const dbRes = await fetch("http://localhost:3000/api/actions");
          setServiceStatus((prev) => ({ ...prev, database: dbRes.ok || dbRes.status === 500 }));
        } catch {
          setServiceStatus((prev) => ({ ...prev, database: false }));
        }

        // Fetch proposals
        try {
          const proposalsRes = await fetch("http://localhost:3000/api/actions?limit=10");
          if (proposalsRes.ok) {
            const data = await proposalsRes.json();
            setProposals(data.proposals || []);
          }
        } catch (error) {
          console.error("Failed to fetch proposals:", error);
        }
      } finally {
        setLoading(false);
      }
    }

    fetchStatus();
    const interval = setInterval(fetchStatus, 30000);
    return () => clearInterval(interval);
  }, []);

  return (
    <main className="min-h-screen bg-zinc-50 dark:bg-black p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
            ExecOps
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 mt-2">
            Event-driven vertical agentic ops for SaaS founders
          </p>
        </header>

        {/* Navigation Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 mb-8">
          <NavCard
            href="/inbox"
            title="Inbox"
            description="Review and approve action proposals"
            icon="📥"
          />
          <NavCard
            href="/canvas"
            title="Canvas"
            description="Natural language analytics queries"
            icon="📊"
          />
          <NavCard
            href="http://localhost:8000/docs"
            title="API Docs"
            description="FastAPI documentation"
            icon="📚"
            external
          />
        </div>

        {/* Service Status */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
            Service Status
          </h2>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
            <div className="p-4 bg-white dark:bg-zinc-900 rounded-lg shadow">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">AI Service</p>
              <StatusBadge active={serviceStatus.ai} />
              <p className="text-xs text-zinc-400 mt-1">localhost:8000</p>
            </div>
            <div className="p-4 bg-white dark:bg-zinc-900 rounded-lg shadow">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">Database</p>
              <StatusBadge active={serviceStatus.database} />
              <p className="text-xs text-zinc-400 mt-1">PostgreSQL</p>
            </div>
            <div className="p-4 bg-white dark:bg-zinc-900 rounded-lg shadow">
              <p className="text-sm text-zinc-500 dark:text-zinc-400">Proposals</p>
              <span className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
                {proposals.length}
              </span>
              <p className="text-xs text-zinc-400 mt-1">Pending review</p>
            </div>
          </div>
        </section>

        {/* Recent Proposals */}
        <section>
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">
              Recent Proposals
            </h2>
            <a
              href="/inbox"
              className="text-sm text-blue-600 hover:text-blue-700 dark:text-blue-400"
            >
              View all →
            </a>
          </div>
          {loading ? (
            <p className="text-zinc-500">Loading...</p>
          ) : proposals.length === 0 ? (
            <div className="p-8 text-center bg-white dark:bg-zinc-900 rounded-lg shadow">
              <p className="text-zinc-500 dark:text-zinc-400">
                No proposals yet. Events will trigger action proposals.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {proposals.slice(0, 6).map((proposal) => (
                <ProposalCard key={proposal.id} proposal={proposal} />
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}

function NavCard({
  href,
  title,
  description,
  icon,
  external,
}: {
  href: string;
  title: string;
  description: string;
  icon: string;
  external?: boolean;
}) {
  const content = (
    <div className="p-4 bg-white dark:bg-zinc-900 rounded-lg shadow hover:shadow-md transition-shadow cursor-pointer h-full">
      <div className="flex items-center gap-3">
        <span className="text-2xl">{icon}</span>
        <div>
          <p className="font-semibold text-zinc-900 dark:text-zinc-100">{title}</p>
          <p className="text-sm text-zinc-500 dark:text-zinc-400">{description}</p>
        </div>
      </div>
    </div>
  );

  if (external) {
    return (
      <a href={href} target="_blank" rel="noopener noreferrer">
        {content}
      </a>
    );
  }

  return <a href={href}>{content}</a>;
}
