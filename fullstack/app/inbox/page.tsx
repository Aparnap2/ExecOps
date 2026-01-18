"use client";

import { useState, useEffect } from "react";
import type { ActionProposal } from "@/lib/types";

export default function InboxPage() {
  const [proposals, setProposals] = useState<ActionProposal[]>([]);
  const [loading, setLoading] = useState(true);
  const [filter, setFilter] = useState<"all" | "pending" | "approved" | "rejected">("all");

  useEffect(() => {
    async function fetchProposals() {
      try {
        const url = filter === "all"
          ? "http://localhost:3000/api/actions"
          : `http://localhost:3000/api/actions?status=${filter}`;
        const res = await fetch(url);
        if (res.ok) {
          const data = await res.json();
          setProposals(data.proposals || []);
        }
      } catch (error) {
        console.error("Failed to fetch proposals:", error);
      } finally {
        setLoading(false);
      }
    }

    fetchProposals();
  }, [filter]);

  async function handleApprove(id: string) {
    try {
      const res = await fetch(`http://localhost:3000/api/actions/${id}/approve`, {
        method: "POST",
      });
      if (res.ok) {
        setProposals(proposals.map(p =>
          p.id === id ? { ...p, status: "approved" as const } : p
        ));
      }
    } catch (error) {
      console.error("Failed to approve proposal:", error);
    }
  }

  async function handleReject(id: string) {
    try {
      const res = await fetch(`http://localhost:3000/api/actions/${id}/reject`, {
        method: "POST",
      });
      if (res.ok) {
        setProposals(proposals.map(p =>
          p.id === id ? { ...p, status: "rejected" as const } : p
        ));
      }
    } catch (error) {
      console.error("Failed to reject proposal:", error);
    }
  }

  const pendingProposals = proposals.filter(p => p.status === "pending" || p.status === "pending_approval");
  const otherProposals = proposals.filter(p => p.status !== "pending" && p.status !== "pending_approval");

  return (
    <main className="min-h-screen bg-zinc-50 dark:bg-black p-8">
      <div className="max-w-6xl mx-auto">
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
            Inbox
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 mt-2">
            Review and approve action proposals
          </p>
        </header>

        {/* Filter Tabs */}
        <div className="flex gap-2 mb-6">
          {(["all", "pending", "approved", "rejected"] as const).map((f) => (
            <button
              key={f}
              onClick={() => setFilter(f)}
              className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                filter === f
                  ? "bg-zinc-900 text-white dark:bg-white dark:text-black"
                  : "bg-white text-zinc-600 dark:bg-zinc-900 dark:text-zinc-400 hover:bg-zinc-100 dark:hover:bg-zinc-800"
              }`}
            >
              {f.charAt(0).toUpperCase() + f.slice(1)}
            </button>
          ))}
        </div>

        {loading ? (
          <p className="text-zinc-500">Loading...</p>
        ) : proposals.length === 0 ? (
          <div className="p-8 text-center bg-white dark:bg-zinc-900 rounded-lg shadow">
            <p className="text-zinc-500 dark:text-zinc-400">
              No proposals found.
            </p>
          </div>
        ) : (
          <div className="space-y-6">
            {/* Pending Section */}
            {pendingProposals.length > 0 && filter === "all" && (
              <section>
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
                  Pending Review ({pendingProposals.length})
                </h2>
                <div className="grid grid-cols-1 gap-4">
                  {pendingProposals.map((proposal) => (
                    <ProposalCard
                      key={proposal.id}
                      proposal={proposal}
                      onApprove={handleApprove}
                      onReject={handleReject}
                    />
                  ))}
                </div>
              </section>
            )}

            {/* Other Proposals */}
            {otherProposals.length > 0 && (
              <section>
                <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
                  {filter === "all" ? "Processed" : "Results"}
                </h2>
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  {otherProposals.map((proposal) => (
                    <ProposalCard
                      key={proposal.id}
                      proposal={proposal}
                      onApprove={handleApprove}
                      onReject={handleReject}
                    />
                  ))}
                </div>
              </section>
            )}
          </div>
        )}
      </div>
    </main>
  );
}

function ProposalCard({
  proposal,
  onApprove,
  onReject,
}: {
  proposal: ActionProposal;
  onApprove: (id: string) => void;
  onReject: (id: string) => void;
}) {
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
      className={`p-6 bg-white dark:bg-zinc-900 rounded-lg shadow border-l-4 ${urgencyColors[proposal.urgency]}`}
    >
      <div className="flex justify-between items-start mb-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100 capitalize">
              {proposal.vertical.replace("_", " ")}
            </span>
            <span className="text-xs text-zinc-400">•</span>
            <span className="text-xs text-zinc-500 dark:text-zinc-400">
              {proposal.action_type}
            </span>
          </div>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
            {new Date(proposal.created_at).toLocaleString()}
          </p>
        </div>
        <div className="flex items-center gap-2">
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

      <div className="space-y-3 mb-4">
        {proposal.context_summary && (
          <div>
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
              Summary
            </p>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              {proposal.context_summary}
            </p>
          </div>
        )}
        {proposal.reasoning && (
          <div>
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
              Reasoning
            </p>
            <p className="text-sm text-zinc-700 dark:text-zinc-300">
              {proposal.reasoning}
            </p>
          </div>
        )}
        {Object.keys(proposal.payload || {}).length > 0 && (
          <div>
            <p className="text-xs font-medium text-zinc-500 dark:text-zinc-400 uppercase">
              Proposed Action
            </p>
            <pre className="text-xs bg-zinc-100 dark:bg-zinc-800 p-2 rounded overflow-x-auto mt-1">
              {JSON.stringify(proposal.payload, null, 2)}
            </pre>
          </div>
        )}
      </div>

      <div className="flex items-center justify-between pt-4 border-t border-zinc-100 dark:border-zinc-800">
        <p className="text-xs text-zinc-500">
          Confidence: {(proposal.confidence * 100).toFixed(0)}%
        </p>
        {(proposal.status === "pending" || proposal.status === "pending_approval") && (
          <div className="flex gap-2">
            <button
              onClick={() => onApprove(proposal.id)}
              className="px-4 py-2 text-sm bg-green-600 text-white rounded-lg hover:bg-green-700 transition-colors"
            >
              Approve
            </button>
            <button
              onClick={() => onReject(proposal.id)}
              className="px-4 py-2 text-sm bg-red-600 text-white rounded-lg hover:bg-red-700 transition-colors"
            >
              Reject
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
