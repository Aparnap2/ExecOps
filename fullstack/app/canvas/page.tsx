"use client";

import { useState, useRef, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  MetricCard,
  Sparkline,
} from "@/components/canvas/metric-card";
import { BarChart } from "@/components/canvas/bar-chart";
import { DonutChart } from "@/components/canvas/donut-chart";
import { DataTable } from "@/components/canvas/data-table";
import { Search, Sparkles, TrendingUp, DollarSign, AlertCircle, FileText, Loader2, Zap, Users, Server, Activity } from "lucide-react";

// v2 Generative UI event types
interface GenerativeEvent {
  type: string;
  message?: string;
  query?: string;
  function_calls?: Array<{ name: string; reason: string }>;
  function?: string;
  progress?: string;
  data?: Record<string, unknown>;
  component_hint?: string;
  ui_components?: Array<{ function: string; component: string }>;
  composed?: {
    component_instructions: Array<{
      component: string;
      data: Record<string, unknown>;
      config: Record<string, unknown>;
    }>;
    suggested_questions: string[];
  };
  timestamp: string;
}

// v2 Query presets with more categories
const QUERY_PRESETS = [
  // Finance
  { label: "Runway", query: "What's our runway and cash forecast?", icon: "📊", category: "finance" },
  { label: "Burn Rate", query: "Show me burn rate by category", icon: "🔥", category: "finance" },
  { label: "Revenue", query: "What are our revenue metrics?", icon: "📈", category: "finance" },
  { label: "Compare", query: "How did revenue change this month vs last?", icon: "📉", category: "finance" },
  // Operations
  { label: "Churn", query: "Show me churn by customer segment", icon: "📉", category: "customers" },
  { label: "Customers", query: "What are our CAC and LTV metrics?", icon: "👥", category: "customers" },
  { label: "Team", query: "How's our engineering team velocity?", icon: "🚀", category: "team" },
  { label: "Infrastructure", query: "Show me cloud infrastructure costs", icon: "☁️", category: "infrastructure" },
  // Sales
  { label: "Pipeline", query: "What's our sales pipeline value?", icon: "💼", category: "sales" },
  { label: "Risk", query: "Give me an overall risk analysis", icon: "⚠️", category: "operations" },
];

export default function CanvasPage() {
  const [query, setQuery] = useState("");
  const [events, setEvents] = useState<GenerativeEvent[]>([]);
  const [isStreaming, setIsStreaming] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [suggestedQuestions, setSuggestedQuestions] = useState<string[]>([]);
  const eventsRef = useRef<GenerativeEvent[]>([]);

  // Keep events ref in sync with state
  useEffect(() => {
    eventsRef.current = events;
  }, [events]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    if (!query.trim()) return;

    setIsStreaming(true);
    setError(null);
    setSuggestedQuestions([]);
    setEvents([]);

    try {
      const encodedQuery = encodeURIComponent(query);
      const response = await fetch(`/generative_ui/stream?query=${encodedQuery}`);

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}: ${response.statusText}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error("No response body");

      const decoder = new TextDecoder();

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        const chunk = decoder.decode(value);
        const lines = chunk.split("\n");

        for (const line of lines) {
          if (line.startsWith("data:")) {
            try {
              const data = JSON.parse(line.slice(5)) as GenerativeEvent;
              setEvents(prev => [...prev, data]);

              // Extract suggested questions from complete event
              if (data.type === "complete" && data.composed?.suggested_questions) {
                setSuggestedQuestions(data.composed.suggested_questions);
              }
            } catch {
              // Skip invalid JSON
            }
          }
        }
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to fetch analytics");
    } finally {
      setIsStreaming(false);
    }
  }

  const latestEvent = events[events.length - 1];
  const isComplete = latestEvent?.type === "complete";

  return (
    <main className="min-h-screen bg-zinc-50 dark:bg-black">
      <div className="max-w-6xl mx-auto p-8">
        {/* Header */}
        <header className="mb-8">
          <div className="flex items-center gap-3 mb-2">
            <div className="p-2 bg-zinc-900 dark:bg-white rounded-lg">
              <Sparkles className="w-5 h-5 text-white dark:text-black" />
            </div>
            <h1 className="text-3xl font-bold text-zinc-900 dark:text-zinc-100">
              Canvas
            </h1>
            <span className="px-2 py-0.5 text-xs font-medium bg-blue-100 text-blue-700 dark:bg-blue-900/30 dark:text-blue-400 rounded">
              v2 Generative UI
            </span>
          </div>
          <p className="text-zinc-600 dark:text-zinc-400">
            AI-powered business analytics with dynamic visualizations
          </p>
        </header>

        {/* Query Input */}
        <form onSubmit={handleSubmit} className="mb-8">
          <div className="relative">
            <Search className="absolute left-4 top-1/2 -translate-y-1/2 w-5 h-5 text-zinc-400" />
            <input
              type="text"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Ask anything: 'How is our team velocity?', 'Show me churn by segment', 'Forecast cash for 6 months'..."
              className="w-full pl-12 pr-32 py-4 bg-white dark:bg-zinc-900 border border-zinc-300 dark:border-zinc-700 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 text-lg"
            />
            <button
              type="submit"
              disabled={isStreaming || !query.trim()}
              className="absolute right-2 top-1/2 -translate-y-1/2 px-6 py-2 bg-zinc-900 text-white dark:bg-white dark:text-black rounded-lg hover:opacity-90 disabled:opacity-50 disabled:cursor-not-allowed font-medium transition-opacity flex items-center gap-2"
            >
              {isStreaming ? (
                <>
                  <Loader2 className="w-4 h-4 animate-spin" />
                  Analyzing...
                </>
              ) : (
                <>
                  <Zap className="w-4 h-4" />
                  Generate
                </>
              )}
            </button>
          </div>
        </form>

        {/* Error Display */}
        {error && (
          <div className="mb-6 p-4 bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800 rounded-lg text-red-700 dark:text-red-400 flex items-center gap-2">
            <AlertCircle className="w-5 h-5" />
            {error}
          </div>
        )}

        {/* Streaming Status */}
        {isStreaming && (
          <StreamingStatus events={events} />
        )}

        {/* Quick Query Buttons */}
        <div className="mb-8">
          <p className="text-sm text-zinc-500 dark:text-zinc-400 mb-3 font-medium">
            Suggested queries
          </p>
          <div className="grid grid-cols-2 md:grid-cols-5 gap-2">
            {QUERY_PRESETS.map((preset) => (
              <button
                key={preset.query}
                onClick={() => {
                  setQuery(preset.query);
                }}
                className="p-3 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-lg hover:bg-zinc-50 dark:hover:bg-zinc-800 hover:border-zinc-300 dark:hover:border-zinc-700 transition-all group text-left"
              >
                <div className="flex items-center gap-2 mb-1">
                  <span className="text-lg group-hover:scale-110 transition-transform">
                    {preset.icon}
                  </span>
                  <span className="text-xs font-medium text-zinc-500 dark:text-zinc-400 capitalize">
                    {preset.category}
                  </span>
                </div>
                <span className="text-sm font-medium text-zinc-900 dark:text-zinc-100 line-clamp-2">
                  {preset.label}
                </span>
              </button>
            ))}
          </div>
        </div>

        {/* Results Display */}
        {isComplete && latestEvent?.composed && (
          <GenerativeResultDisplay
            query={query}
            events={events}
            composed={latestEvent.composed}
            onQuestionClick={(q) => setQuery(q)}
          />
        )}

        {/* Suggested Follow-up Questions */}
        {suggestedQuestions.length > 0 && (
          <div className="mt-8 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl">
            <p className="text-sm font-medium text-blue-800 dark:text-blue-300 mb-3 flex items-center gap-2">
              <Sparkles className="w-4 h-4" />
              Suggested follow-up questions
            </p>
            <div className="flex flex-wrap gap-2">
              {suggestedQuestions.map((sq, i) => (
                <button
                  key={i}
                  onClick={() => setQuery(sq)}
                  className="px-3 py-1.5 bg-white dark:bg-zinc-800 border border-blue-200 dark:border-blue-700 rounded-lg text-sm text-blue-700 dark:text-blue-300 hover:bg-blue-100 dark:hover:bg-blue-800/50 transition-colors"
                >
                  {sq}
                </button>
              ))}
            </div>
          </div>
        )}

        {/* Available Query Types */}
        <div className="mt-12 p-6 bg-zinc-100 dark:bg-zinc-900 rounded-xl">
          <h2 className="text-sm font-semibold text-zinc-700 dark:text-zinc-300 mb-4 flex items-center gap-2">
            <FileText className="w-4 h-4" />
            v2 Query Types (Generative UI)
          </h2>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
            <QueryCategory
              title="Finance"
              queries={["runway", "burn rate", "revenue", "compare periods", "forecast"]}
              icon={<DollarSign className="w-4 h-4" />}
            />
            <QueryCategory
              title="Customers"
              queries={["churn", "CAC/LTV", "retention", "cohort analysis"]}
              icon={<Users className="w-4 h-4" />}
            />
            <QueryCategory
              title="Team"
              queries={["velocity", "commits", "PR metrics", "deploy frequency"]}
              icon={<Activity className="w-4 h-4" />}
            />
            <QueryCategory
              title="Infrastructure"
              queries={["AWS costs", "cloud spend", "optimization"]}
              icon={<Server className="w-4 h-4" />}
            />
          </div>
        </div>
      </div>
    </main>
  );
}

function StreamingStatus({ events }: { events: GenerativeEvent[] }) {
  const currentEvent = events[events.length - 1];

  return (
    <div className="mb-6 p-4 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-800 rounded-xl">
      <div className="flex items-center gap-3">
        <Loader2 className="w-5 h-5 text-blue-600 dark:text-blue-400 animate-spin" />
        <div className="flex-1">
          <p className="text-sm font-medium text-blue-800 dark:text-blue-300">
            {currentEvent?.message || "Analyzing your query..."}
          </p>
          <p className="text-xs text-blue-600 dark:text-blue-400">
            {currentEvent?.function && `Calling: ${currentEvent.function}`}
            {currentEvent?.progress && ` • ${currentEvent.progress}`}
          </p>
        </div>
      </div>
    </div>
  );
}

function QueryCategory({ title, queries, icon }: { title: string; queries: string[]; icon: React.ReactNode }) {
  return (
    <div className="p-3 bg-white dark:bg-zinc-800 rounded-lg">
      <div className="flex items-center gap-2 mb-2 text-zinc-700 dark:text-zinc-300">
        {icon}
        <span className="font-medium">{title}</span>
      </div>
      <ul className="space-y-1">
        {queries.map((q) => (
          <li key={q} className="text-xs text-zinc-500 dark:text-zinc-400 flex items-center gap-1">
            <span className="w-1 h-1 bg-zinc-400 rounded-full" />
            {q}
          </li>
        ))}
      </ul>
    </div>
  );
}

function GenerativeResultDisplay({
  query,
  events,
  composed,
  onQuestionClick,
}: {
  query: string;
  events: GenerativeEvent[];
  composed: GenerativeEvent["composed"];
  onQuestionClick: (q: string) => void;
}) {
  return (
    <div className="space-y-6">
      {/* Query context */}
      <div className="flex items-center justify-between p-4 bg-white dark:bg-zinc-900 border border-zinc-200 dark:border-zinc-800 rounded-xl">
        <div className="flex items-center gap-3">
          <div className="p-2 bg-blue-100 dark:bg-blue-900/30 rounded-lg">
            <Search className="w-4 h-4 text-blue-600 dark:text-blue-400" />
          </div>
          <div>
            <p className="text-sm text-zinc-500 dark:text-zinc-400">Query</p>
            <p className="font-medium text-zinc-900 dark:text-zinc-100">{query}</p>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="px-2 py-1 bg-green-100 text-green-700 dark:bg-green-900/30 dark:text-green-400 rounded text-xs font-medium">
            Complete
          </span>
        </div>
      </div>

      {/* Dynamically rendered components based on LLM decision */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {composed?.component_instructions.map((instruction, i) => (
          <ComponentRenderer
            key={i}
            component={instruction.component}
            data={instruction.data}
            config={instruction.config}
          />
        ))}
      </div>
    </div>
  );
}

function ComponentRenderer({
  component,
  data,
  config,
}: {
  component: string;
  data: Record<string, unknown>;
  config: Record<string, unknown>;
}) {
  switch (component) {
    case "bar_chart":
      return <BarChartComponent data={data} config={config} />;
    case "donut_chart":
      return <DonutChartComponent data={data} config={config} />;
    case "sparkline":
      return <SparklineComponent data={data} config={config} />;
    case "data_table":
      return <DataTableComponent data={data} config={config} />;
    case "metrics_grid":
      return <MetricsGridComponent data={data} config={config} />;
    case "metric_card":
    default:
      return <MetricsGridComponent data={data} config={config} />;
  }
}

function BarChartComponent({ data, config }: { data: Record<string, unknown>; config: Record<string, unknown> }) {
  // Adapt various data shapes to bar chart format
  let chartData: Array<{ label: string; value: number; color: string }> = [];

  if (data.by_tag) {
    const byTag = data.by_tag as Record<string, { total: number }>;
    chartData = Object.entries(byTag).map(([label, info], i) => ({
      label,
      value: info.total,
      color: ["#6366f1", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899", "#14b8a6"][i % 6],
    }));
  } else if (data.by_service) {
    const byService = data.by_service as Record<string, { cost: number }>;
    chartData = Object.entries(byService).map(([label, info], i) => ({
      label,
      value: info.cost,
      color: ["#6366f1", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"][i % 5],
    }));
  } else if (data.by_segment) {
    const bySegment = data.by_segment as Record<string, { churn_rate?: number; revenue_at_risk?: number }>;
    chartData = Object.entries(bySegment).map(([label, info], i) => ({
      label,
      value: info.revenue_at_risk || info.churn_rate || 0,
      color: ["#ef4444", "#f59e0b", "#10b981"][i % 3],
    }));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">
          {Object.keys(data)[0].replace(/_/g, " ").replace(/by /gi, "").replace(/\b\w/g, l => l.toUpperCase())}
        </CardTitle>
      </CardHeader>
      <CardContent>
        {chartData.length > 0 ? (
          <BarChart data={chartData} height={(config.height as number) || 180} />
        ) : (
          <p className="text-sm text-zinc-500">No chart data available</p>
        )}
      </CardContent>
    </Card>
  );
}

function DonutChartComponent({ data, config }: { data: Record<string, unknown>; config: Record<string, unknown> }) {
  let chartData: Array<{ label: string; value: number; color: string }> = [];

  if (data.by_category) {
    const byCategory = data.by_category as Record<string, number>;
    chartData = Object.entries(byCategory).map(([label, value], i) => ({
      label,
      value,
      color: ["#6366f1", "#10b981", "#f59e0b", "#8b5cf6", "#ec4899"][i % 5],
    }));
  } else if (data.by_segment) {
    const bySegment = data.by_segment as Record<string, { churn_rate?: number }>;
    chartData = Object.entries(bySegment).map(([label, info], i) => ({
      label,
      value: info.churn_rate || 0,
      color: ["#ef4444", "#f59e0b", "#10b981"][i % 3],
    }));
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Distribution</CardTitle>
      </CardHeader>
      <CardContent className="flex justify-center">
        {chartData.length > 0 ? (
          <DonutChart data={chartData} size={(config.innerRadius as number) ? 160 : 200} showLegend={config.showLegend as boolean ?? true} />
        ) : (
          <p className="text-sm text-zinc-500">No data available</p>
        )}
      </CardContent>
    </Card>
  );
}

function SparklineComponent({ data, config }: { data: Record<string, unknown>; config: Record<string, unknown> }) {
  const projection = data.projection as Array<{ projected_cash: number }> || [];
  const chartData = projection.map(p => p.projected_cash);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Cash Projection</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="flex items-end gap-4 h-24">
          <Sparkline
            data={chartData}
            width={(config.width as number) || 300}
            height={(config.height as number) || 80}
            color="#10b981"
          />
          <div className="flex-1">
            <p className="text-xs text-zinc-500 mb-1">Projected cash (6 mo)</p>
            <p className="text-xl font-bold text-zinc-900 dark:text-zinc-100">
              ${chartData[chartData.length - 1]?.toLocaleString() || "N/A"}
            </p>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

function DataTableComponent({ data, config }: { data: Record<string, unknown>; config: Record<string, unknown> }) {
  const byCohort = data.by_cohort as Record<string, { revenue: number; customers: number; retention: number }> || {};

  const tableData = Object.entries(byCohort).map(([cohort, info]) => ({
    cohort,
    revenue: info.revenue,
    customers: info.customers,
    retention: `${info.retention}%`,
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Cohort Analysis</CardTitle>
      </CardHeader>
      <CardContent>
        <DataTable
          data={tableData}
          columns={[
            { key: "cohort", label: "Cohort", sortable: true },
            { key: "revenue", label: "Revenue", sortable: true, align: "right", render: (v) => `$${Number(v).toLocaleString()}` },
            { key: "customers", label: "Customers", sortable: true, align: "right" },
            { key: "retention", label: "Retention", sortable: true, align: "right" },
          ]}
        />
      </CardContent>
    </Card>
  );
}

function MetricsGridComponent({ data, config }: { data: Record<string, unknown>; config: Record<string, unknown> }) {
  // Flatten nested data into metrics
  const metrics: Array<{ title: string; value: string | number; subtitle?: string }> = [];

  const flatten = (obj: Record<string, unknown>, prefix = "") => {
    for (const [key, value] of Object.entries(obj)) {
      const title = prefix + key.replace(/_/g, " ").replace(/\b\w/g, l => l.toUpperCase());
      if (typeof value === "number" && !key.includes("_history") && !key.includes("_trend")) {
        // Format based on key
        let formattedValue = value;
        let subtitle: string | undefined;

        if (key.includes("rate") || key.includes("pct") || key.includes("percent")) {
          formattedValue = `${value}%`;
        } else if (key.includes("cost") || key.includes("revenue") || key.includes("cash") || key.includes("spend")) {
          formattedValue = `$${value.toLocaleString()}`;
        } else if (key.includes("score") || key.includes("retention")) {
          formattedValue = `${value}%`;
        } else if (key.includes("ratio")) {
          formattedValue = `${value}x`;
        }

        if (key.includes("trend")) {
          subtitle = value > 0 ? "Increasing" : value < 0 ? "Decreasing" : "Stable";
        }

        metrics.push({ title, value: formattedValue, subtitle });
      } else if (typeof value === "object" && value !== null && !Array.isArray(value)) {
        flatten(value as Record<string, unknown>, title + " ");
      }
    }
  };

  flatten(data);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="text-sm font-medium">Key Metrics</CardTitle>
      </CardHeader>
      <CardContent>
        <div className="grid grid-cols-2 md:grid-cols-3 gap-4">
          {metrics.slice(0, 8).map((metric) => (
            <div key={metric.title} className="p-3 bg-zinc-50 dark:bg-zinc-800/50 rounded-lg">
              <p className="text-xs text-zinc-500 dark:text-zinc-400 mb-1">{metric.title}</p>
              <p className="text-lg font-semibold text-zinc-900 dark:text-zinc-100">{metric.value}</p>
              {metric.subtitle && (
                <p className="text-xs text-zinc-400">{metric.subtitle}</p>
              )}
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}
