"use client";

import { useState, useEffect } from "react";
import type { Decision, DecisionState } from "@/lib/types";

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

function DecisionCard({ decision }: { decision: Decision }) {
  const stateColors: Record<DecisionState, string> = {
    CONFIDENT: "border-l-green-500",
    UNCERTAIN: "border-l-yellow-500",
    ESCALATE: "border-l-red-500",
  };

  return (
    <div
      className={`p-4 bg-white dark:bg-zinc-900 rounded-lg shadow border-l-4 ${stateColors[decision.state]}`}
    >
      <div className="flex justify-between items-start">
        <div>
          <p className="text-sm font-medium text-zinc-900 dark:text-zinc-100">
            {decision.objective.replace("_", " ")}
          </p>
          <p className="text-xs text-zinc-500 dark:text-zinc-400 mt-1">
            {new Date(decision.created_at).toLocaleString()}
          </p>
        </div>
        <span
          className={`px-2 py-1 text-xs font-semibold rounded ${
            decision.state === "CONFIDENT"
              ? "bg-green-100 text-green-800"
              : decision.state === "UNCERTAIN"
              ? "bg-yellow-100 text-yellow-800"
              : "bg-red-100 text-red-800"
          }`}
        >
          {decision.state}
        </span>
      </div>
      <p className="mt-2 text-sm text-zinc-600 dark:text-zinc-300">{decision.summary}</p>
      <p className="mt-2 text-xs text-zinc-500">
        Confidence: {(decision.confidence * 100).toFixed(0)}%
      </p>
    </div>
  );
}

export default function Home() {
  const [serviceStatus, setServiceStatus] = useState<ServiceStatus>({
    ai: false,
    database: false,
  });
  const [decisions, setDecisions] = useState<Decision[]>([]);
  const [loading, setLoading] = useState(true);
  const [testingDecision, setTestingDecision] = useState(false);
  const [testResult, setTestResult] = useState<string | null>(null);

  // Fetch service status and decisions
  useEffect(() => {
    async function fetchStatus() {
      try {
        // Check AI service
        const aiRes = await fetch("http://localhost:8000/health");
        setServiceStatus((prev) => ({ ...prev, ai: aiRes.ok }));

        // Check database via API
        const dbRes = await fetch("http://localhost:3000/api/ai/decide");
        setServiceStatus((prev) => ({ ...prev, database: dbRes.ok || dbRes.status === 500 }));

        // Fetch decisions
        const decisionsRes = await fetch("http://localhost:3000/api/ai/decide");
        if (decisionsRes.ok) {
          const data = await decisionsRes.json();
          setDecisions(data.decisions || []);
        }
      } catch (error) {
        console.error("Status check failed:", error);
      } finally {
        setLoading(false);
      }
    }

    fetchStatus();
    const interval = setInterval(fetchStatus, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, []);

  // Test decision endpoint
  async function runTestDecision() {
    setTestingDecision(true);
    setTestResult(null);

    try {
      const response = await fetch("http://localhost:3000/api/ai/decide", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          objective: "lead_hygiene",
          events: [
            {
              source: "hubspot",
              occurred_at: new Date().toISOString(),
              data: {
                contact_id: "test_contact_001",
                email: "test@example.com",
                status: null, // Missing status - should trigger escalation
              },
            },
          ],
          constraints: { stale_threshold_hours: 48 },
        }),
      });

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
      }

      const data = await response.json();
      setTestResult(
        `State: ${data.state}\nSummary: ${data.summary}\nConfidence: ${(data.confidence * 100).toFixed(0)}%\nSOPs: ${data.executed_sops?.join(", ") || "none"}`
      );
    } catch (error) {
      setTestResult(`Error: ${error instanceof Error ? error.message : "Unknown error"}`);
    } finally {
      setTestingDecision(false);
    }
  }

  return (
    <main className="min-h-screen bg-zinc-50 dark:bg-black p-8">
      <div className="max-w-6xl mx-auto">
        {/* Header */}
        <header className="mb-8">
          <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
            FounderOS
          </h1>
          <p className="text-zinc-600 dark:text-zinc-400 mt-2">
            Agentic AI automation for SaaS founders
          </p>
        </header>

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
              <p className="text-sm text-zinc-500 dark:text-zinc-400">Decisions</p>
              <span className="text-2xl font-bold text-zinc-900 dark:text-zinc-100">
                {decisions.length}
              </span>
              <p className="text-xs text-zinc-400 mt-1">Total processed</p>
            </div>
          </div>
        </section>

        {/* Quick Actions */}
        <section className="mb-8">
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
            Quick Actions
          </h2>
          <div className="flex flex-wrap gap-4">
            <button
              onClick={runTestDecision}
              disabled={testingDecision || !serviceStatus.ai}
              className="px-4 py-2 bg-blue-600 text-white rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed"
            >
              {testingDecision ? "Running..." : "Test Lead Hygiene SOP"}
            </button>
            <a
              href="/events"
              className="px-4 py-2 bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100 rounded-lg hover:bg-zinc-200 dark:hover:bg-zinc-700"
            >
              View Events
            </a>
            <a
              href="http://localhost:8000/docs"
              target="_blank"
              rel="noopener noreferrer"
              className="px-4 py-2 bg-zinc-100 text-zinc-900 dark:bg-zinc-800 dark:text-zinc-100 rounded-lg hover:bg-zinc-200 dark:hover:bg-zinc-700"
            >
              API Docs
            </a>
          </div>

          {testResult && (
            <div className="mt-4 p-4 bg-zinc-900 text-zinc-100 rounded-lg font-mono text-sm whitespace-pre-wrap">
              {testResult}
            </div>
          )}
        </section>

        {/* Recent Decisions */}
        <section>
          <h2 className="text-lg font-semibold text-zinc-900 dark:text-zinc-100 mb-4">
            Recent Decisions
          </h2>
          {loading ? (
            <p className="text-zinc-500">Loading...</p>
          ) : decisions.length === 0 ? (
            <div className="p-8 text-center bg-white dark:bg-zinc-900 rounded-lg shadow">
              <p className="text-zinc-500 dark:text-zinc-400">
                No decisions yet. Run a test to get started.
              </p>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
              {decisions.slice(0, 6).map((decision) => (
                <DecisionCard key={decision.id} decision={decision} />
              ))}
            </div>
          )}
        </section>
      </div>
    </main>
  );
}
