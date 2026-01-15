/**
 * ExecOps Inbox Component
 *
 * Displays action proposals requiring founder attention.
 * Supports filtering by vertical, status, and urgency.
 */

"use client";

import { useState, useEffect } from "react";

// =============================================================================
// Types
// =============================================================================

export type ActionProposalStatus = "pending" | "pending_approval" | "approved" | "rejected" | "executed";
export type ActionUrgency = "low" | "medium" | "high" | "critical";
export type ActionVertical = "release" | "customer_fire" | "runway" | "team_pulse";

export interface ActionProposal {
  id: string;
  status: ActionProposalStatus;
  urgency: ActionUrgency;
  vertical: ActionVertical;
  action_type: string;
  payload: Record<string, unknown>;
  reasoning: string;
  context_summary: string;
  confidence: number;
  created_at: string;
  approved_at: string | null;
  executed_at: string | null;
}

// =============================================================================
// Constants
// =============================================================================

const URGENCY_COLORS: Record<ActionUrgency, string> = {
  critical: "bg-red-100 text-red-800 border-red-200 dark:bg-red-900/30 dark:text-red-300",
  high: "bg-orange-100 text-orange-800 border-orange-200 dark:bg-orange-900/30 dark:text-orange-300",
  medium: "bg-yellow-100 text-yellow-800 border-yellow-200 dark:bg-yellow-900/30 dark:text-yellow-300",
  low: "bg-green-100 text-green-800 border-green-200 dark:bg-green-900/30 dark:text-green-300",
};

const VERTICAL_LABELS: Record<ActionVertical, string> = {
  release: "Release Hygiene",
  customer_fire: "Customer Fire",
  runway: "Runway/Money",
  team_pulse: "Team Pulse",
};

const VERTICAL_ICONS: Record<ActionVertical, string> = {
  release: "🔴",
  customer_fire: "🔥",
  runway: "💰",
  team_pulse: "👥",
};

const STATUS_CONFIG: Record<ActionProposalStatus, { label: string; color: string }> = {
  pending: { label: "Pending", color: "bg-gray-100 text-gray-800 dark:bg-gray-800 dark:text-gray-300" },
  pending_approval: { label: "Needs Approval", color: "bg-yellow-100 text-yellow-800 dark:bg-yellow-900/30 dark:text-yellow-300" },
  approved: { label: "Approved", color: "bg-green-100 text-green-800 dark:bg-green-900/30 dark:text-green-300" },
  rejected: { label: "Rejected", color: "bg-red-100 text-red-800 dark:bg-red-900/30 dark:text-red-300" },
  executed: { label: "Executed", color: "bg-blue-100 text-blue-800 dark:bg-blue-900/30 dark:text-blue-300" },
};

// =============================================================================
// Helper Functions
// =============================================================================

function formatTimeAgo(dateString: string): string {
  const date = new Date(dateString);
  const now = new Date();
  const seconds = Math.floor((now.getTime() - date.getTime()) / 1000);

  if (seconds < 60) return "Just now";
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
  return `${Math.floor(seconds / 86400)}d ago`;
}

function formatConfidence(confidence: number): string {
  return `${(confidence * 100).toFixed(0)}%`;
}

function getActionTypeLabel(action_type: string): string {
  const labels: Record<string, string> = {
    email: "Email",
    command: "Command",
    slack_dm: "Slack DM",
    webhook: "Webhook",
    api_call: "API Call",
  };
  return labels[action_type] || action_type;
}

// =============================================================================
// Sub-Components
// =============================================================================

function UrgencyBadge({ urgency }: { urgency: ActionUrgency }) {
  return (
    <span
      className={`px-2 py-1 text-xs font-semibold rounded-full border ${URGENCY_COLORS[urgency]}`}
    >
      {urgency.charAt(0).toUpperCase() + urgency.slice(1)}
    </span>
  );
}

function StatusBadge({ status }: { status: ActionProposalStatus }) {
  const config = STATUS_CONFIG[status];
  return (
    <span className={`px-2 py-1 text-xs font-semibold rounded-full ${config.color}`}>
      {config.label}
    </span>
  );
}

function VerticalBadge({ vertical }: { vertical: ActionVertical }) {
  return (
    <span className="inline-flex items-center gap-1 text-sm font-medium text-zinc-700 dark:text-zinc-300">
      <span>{VERTICAL_ICONS[vertical]}</span>
      <span>{VERTICAL_LABELS[vertical]}</span>
    </span>
  );
}

function PayloadPreview({ payload, action_type }: { payload: Record<string, unknown>; action_type: string }) {
  if (action_type === "email") {
    const { to, subject } = payload;
    return (
      <div className="text-sm text-zinc-600 dark:text-zinc-400">
        <p><span className="font-medium">To:</span> {to as string}</p>
        <p><span className="font-medium">Subject:</span> {subject as string}</p>
      </div>
    );
  }

  if (action_type === "command") {
    const { command, working_dir } = payload;
    return (
      <div className="text-sm text-zinc-600 dark:text-zinc-400 font-mono">
        <p className="truncate"><span className="font-medium">Command:</span> {command as string}</p>
        {working_dir && <p><span className="font-medium">Dir:</span> {working_dir as string}</p>}
      </div>
    );
  }

  if (action_type === "slack_dm") {
    const { slack_channel, slack_blocks } = payload;
    return (
      <div className="text-sm text-zinc-600 dark:text-zinc-400">
        <p><span className="font-medium">Channel:</span> {slack_channel as string}</p>
        <p><span className="font-medium">Blocks:</span> {Array.isArray(slack_blocks) ? slack_blocks.length : 0}</p>
      </div>
    );
  }

  // Generic fallback
  const keys = Object.keys(payload).slice(0, 3);
  return (
    <div className="text-sm text-zinc-600 dark:text-zinc-400">
      {keys.map((key) => (
        <p key={key}>
          <span className="font-medium capitalize">{key}:</span> {String(payload[key]).slice(0, 50)}
        </p>
      ))}
    </div>
  );
}

// =============================================================================
// Action Proposal Card
// =============================================================================

function ActionProposalCard({
  proposal,
  onApprove,
  onReject,
}: {
  proposal: ActionProposal;
  onApprove?: (id: string) => void;
  onReject?: (id: string) => void;
}) {
  const showActions = proposal.status === "pending_approval";

  return (
    <div className="bg-white dark:bg-zinc-900 rounded-lg shadow border border-zinc-200 dark:border-zinc-800 overflow-hidden transition-all hover:shadow-md">
      {/* Header */}
      <div className="p-4 border-b border-zinc-100 dark:border-zinc-800">
        <div className="flex items-start justify-between gap-4">
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <VerticalBadge vertical={proposal.vertical} />
              <span className="text-zinc-400 dark:text-zinc-500">•</span>
              <UrgencyBadge urgency={proposal.urgency} />
            </div>
            <h3 className="font-semibold text-zinc-900 dark:text-zinc-100 truncate">
              {getActionTypeLabel(proposal.action_type)}
            </h3>
          </div>
          <StatusBadge status={proposal.status} />
        </div>
      </div>

      {/* Body */}
      <div className="p-4 space-y-3">
        {/* Reasoning */}
        <p className="text-sm text-zinc-700 dark:text-zinc-300 font-medium">
          {proposal.reasoning}
        </p>

        {/* Context Summary */}
        <p className="text-sm text-zinc-500 dark:text-zinc-400 line-clamp-2">
          {proposal.context_summary}
        </p>

        {/* Payload Preview */}
        <div className="pt-2 border-t border-zinc-100 dark:border-zinc-800">
          <PayloadPreview payload={proposal.payload} action_type={proposal.action_type} />
        </div>

        {/* Meta */}
        <div className="flex items-center justify-between pt-2 text-xs text-zinc-400 dark:text-zinc-500">
          <span>{formatTimeAgo(proposal.created_at)}</span>
          <span>Confidence: {formatConfidence(proposal.confidence)}</span>
        </div>
      </div>

      {/* Actions */}
      {showActions && (
        <div className="flex gap-2 p-4 bg-zinc-50 dark:bg-zinc-800/50 border-t border-zinc-100 dark:border-zinc-800">
          {onApprove && (
            <button
              onClick={() => onApprove(proposal.id)}
              className="flex-1 px-4 py-2 bg-green-600 text-white text-sm font-medium rounded-lg hover:bg-green-700 focus:outline-none focus:ring-2 focus:ring-green-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900 transition-colors"
            >
              Approve
            </button>
          )}
          {onReject && (
            <button
              onClick={() => onReject(proposal.id)}
              className="flex-1 px-4 py-2 bg-red-600 text-white text-sm font-medium rounded-lg hover:bg-red-700 focus:outline-none focus:ring-2 focus:ring-red-500 focus:ring-offset-2 dark:focus:ring-offset-zinc-900 transition-colors"
            >
              Reject
            </button>
          )}
        </div>
      )}
    </div>
  );
}

// =============================================================================
// Filter Bar
// =============================================================================

function FilterBar({
  verticals,
  statuses,
  selectedVertical,
  selectedStatus,
  onVerticalChange,
  onStatusChange,
}: {
  verticals: ActionVertical[];
  statuses: ActionProposalStatus[];
  selectedVertical: ActionVertical | "all";
  selectedStatus: ActionProposalStatus | "all";
  onVerticalChange: (v: ActionVertical | "all") => void;
  onStatusChange: (s: ActionProposalStatus | "all") => void;
}) {
  return (
    <div className="flex flex-wrap items-center gap-4 mb-6">
      {/* Vertical Filter */}
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Vertical:</label>
        <select
          value={selectedVertical}
          onChange={(e) => onVerticalChange(e.target.value as ActionVertical | "all")}
          className="px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Verticals</option>
          {verticals.map((v) => (
            <option key={v} value={v}>
              {VERTICAL_LABELS[v]}
            </option>
          ))}
        </select>
      </div>

      {/* Status Filter */}
      <div className="flex items-center gap-2">
        <label className="text-sm font-medium text-zinc-700 dark:text-zinc-300">Status:</label>
        <select
          value={selectedStatus}
          onChange={(e) => onStatusChange(e.target.value as ActionProposalStatus | "all")}
          className="px-3 py-2 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-lg text-sm focus:outline-none focus:ring-2 focus:ring-blue-500"
        >
          <option value="all">All Statuses</option>
          {statuses.map((s) => (
            <option key={s} value={s}>
              {STATUS_CONFIG[s].label}
            </option>
          ))}
        </select>
      </div>
    </div>
  );
}

// =============================================================================
// Main Inbox Component
// =============================================================================

interface InboxProps {
  initialProposals?: ActionProposal[];
  onApprove?: (id: string) => Promise<void>;
  onReject?: (id: string) => Promise<void>;
}

export function Inbox({ initialProposals = [], onApprove, onReject }: InboxProps) {
  const [proposals, setProposals] = useState<ActionProposal[]>(initialProposals);
  const [loading, setLoading] = useState(!initialProposals.length);
  const [selectedVertical, setSelectedVertical] = useState<ActionVertical | "all">("all");
  const [selectedStatus, setSelectedStatus] = useState<ActionProposalStatus | "all">("all");
  const [processingId, setProcessingId] = useState<string | null>(null);

  // Fetch proposals on mount
  useEffect(() => {
    async function fetchProposals() {
      try {
        const res = await fetch("/api/actions");
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

    if (!initialProposals.length) {
      fetchProposals();
    }
  }, [initialProposals.length]);

  // Filter proposals
  const filteredProposals = proposals.filter((p) => {
    const verticalMatch = selectedVertical === "all" || p.vertical === selectedVertical;
    const statusMatch = selectedStatus === "all" || p.status === selectedStatus;
    return verticalMatch && statusMatch;
  });

  // Sort by urgency first, then by date
  const sortedProposals = [...filteredProposals].sort((a, b) => {
    const urgencyOrder: Record<ActionUrgency, number> = { critical: 0, high: 1, medium: 2, low: 3 };
    const urgencyDiff = urgencyOrder[a.urgency] - urgencyOrder[b.urgency];
    if (urgencyDiff !== 0) return urgencyDiff;
    return new Date(b.created_at).getTime() - new Date(a.created_at).getTime();
  });

  // Handle approval/rejection
  const handleAction = async (id: string, action: "approve" | "reject") => {
    setProcessingId(id);
    try {
      const res = await fetch(`/api/actions/${id}/${action}`, { method: "POST" });
      if (res.ok) {
        setProposals((prev) =>
          prev.map((p) =>
            p.id === id
              ? {
                  ...p,
                  status: action === "approve" ? "approved" as const : "rejected" as const,
                  approved_at: action === "approve" ? new Date().toISOString() : null,
                }
              : p
          )
        );
      }
    } catch (error) {
      console.error(`Failed to ${action} proposal:`, error);
    } finally {
      setProcessingId(null);
    }
  };

  // Statistics
  const stats = {
    total: proposals.length,
    pending: proposals.filter((p) => p.status === "pending_approval").length,
    approved: proposals.filter((p) => p.status === "approved").length,
    executed: proposals.filter((p) => p.status === "executed").length,
  };

  return (
    <div className="space-y-6">
      {/* Stats */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="p-4 bg-white dark:bg-zinc-900 rounded-lg shadow border border-zinc-200 dark:border-zinc-800">
          <p className="text-sm text-zinc-500 dark:text-zinc-400">Total</p>
          <p className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">{stats.total}</p>
        </div>
        <div className="p-4 bg-yellow-50 dark:bg-yellow-900/20 rounded-lg shadow border border-yellow-200 dark:border-yellow-800">
          <p className="text-sm text-yellow-700 dark:text-yellow-400">Pending Approval</p>
          <p className="text-2xl font-bold text-yellow-900 dark:text-yellow-300">{stats.pending}</p>
        </div>
        <div className="p-4 bg-green-50 dark:bg-green-900/20 rounded-lg shadow border border-green-200 dark:border-green-800">
          <p className="text-sm text-green-700 dark:text-green-400">Approved</p>
          <p className="text-2xl font-bold text-green-900 dark:text-green-300">{stats.approved}</p>
        </div>
        <div className="p-4 bg-blue-50 dark:bg-blue-900/20 rounded-lg shadow border border-blue-200 dark:border-blue-800">
          <p className="text-sm text-blue-700 dark:text-blue-400">Executed</p>
          <p className="text-2xl font-bold text-blue-900 dark:text-blue-300">{stats.executed}</p>
        </div>
      </div>

      {/* Filter Bar */}
      <FilterBar
        verticals={["release", "customer_fire", "runway", "team_pulse"]}
        statuses={["pending_approval", "approved", "rejected", "executed"]}
        selectedVertical={selectedVertical}
        selectedStatus={selectedStatus}
        onVerticalChange={setSelectedVertical}
        onStatusChange={setSelectedStatus}
      />

      {/* Proposal List */}
      {loading ? (
        <div className="flex items-center justify-center py-12">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-blue-600" />
        </div>
      ) : sortedProposals.length === 0 ? (
        <div className="text-center py-12 bg-zinc-50 dark:bg-zinc-900 rounded-lg border border-dashed border-zinc-300 dark:border-zinc-700">
          <p className="text-zinc-500 dark:text-zinc-400">No action proposals found</p>
          <p className="text-sm text-zinc-400 dark:text-zinc-500 mt-1">
            Events will appear here when they require your attention
          </p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          {sortedProposals.map((proposal) => (
            <ActionProposalCard
              key={proposal.id}
              proposal={proposal}
              onApprove={proposal.status === "pending_approval" ? (id) => handleAction(id, "approve") : undefined}
              onReject={proposal.status === "pending_approval" ? (id) => handleAction(id, "reject") : undefined}
            />
          ))}
        </div>
      )}
    </div>
  );
}
