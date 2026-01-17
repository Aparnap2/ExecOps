"use client";

import { useState, useMemo } from "react";
import { cn } from "@/lib/utils";
import { ChevronUp, ChevronDown, ArrowUpDown } from "lucide-react";

interface Column<T> {
  key: string;
  label: string;
  sortable?: boolean;
  render?: (value: unknown, row: T) => React.ReactNode;
  align?: "left" | "center" | "right";
}

interface DataTableProps<T extends Record<string, unknown>> {
  data: T[];
  columns: Column<T>[];
  title?: string;
  className?: string;
}

export function DataTable<T extends Record<string, unknown>>({
  data,
  columns,
  title,
  className,
}: DataTableProps<T>) {
  const [sortKey, setSortKey] = useState<string | null>(null);
  const [sortDirection, setSortDirection] = useState<"asc" | "desc">("asc");

  const sortedData = useMemo(() => {
    if (!sortKey) return data;

    return [...data].sort((a, b) => {
      const aVal = a[sortKey];
      const bVal = b[sortKey];

      if (typeof aVal === "number" && typeof bVal === "number") {
        return sortDirection === "asc" ? aVal - bVal : bVal - aVal;
      }

      const aStr = String(aVal ?? "").toLowerCase();
      const bStr = String(bVal ?? "").toLowerCase();

      return sortDirection === "asc"
        ? aStr.localeCompare(bStr)
        : bStr.localeCompare(aStr);
    });
  }, [data, sortKey, sortDirection]);

  const handleSort = (key: string) => {
    if (sortKey === key) {
      setSortDirection(sortDirection === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDirection("asc");
    }
  };

  return (
    <div className={cn("w-full overflow-hidden", className)}>
      {title && (
        <p className="text-sm font-medium text-zinc-500 dark:text-zinc-400 mb-3">
          {title}
        </p>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-zinc-200 dark:border-zinc-800">
              {columns.map((col) => (
                <th
                  key={col.key}
                  className={cn(
                    "px-4 py-3 text-left text-xs font-medium text-zinc-500 uppercase tracking-wider",
                    col.sortable && "cursor-pointer hover:text-zinc-700 dark:hover:text-zinc-200",
                    col.align === "center" && "text-center",
                    col.align === "right" && "text-right"
                  )}
                  onClick={() => col.sortable && handleSort(col.key)}
                >
                  <div className="flex items-center gap-1">
                    {col.label}
                    {col.sortable && (
                      <span className="text-zinc-400">
                        {sortKey === col.key ? (
                          sortDirection === "asc" ? (
                            <ChevronUp className="w-3 h-3" />
                          ) : (
                            <ChevronDown className="w-3 h-3" />
                          )
                        ) : (
                          <ArrowUpDown className="w-3 h-3" />
                        )}
                      </span>
                    )}
                  </div>
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-zinc-100 dark:divide-zinc-800">
            {sortedData.map((row, i) => (
              <tr
                key={i}
                className="hover:bg-zinc-50 dark:hover:bg-zinc-900/50 transition-colors"
              >
                {columns.map((col) => (
                  <td
                    key={col.key}
                    className={cn(
                      "px-4 py-3 text-zinc-700 dark:text-zinc-300",
                      col.align === "center" && "text-center",
                      col.align === "right" && "text-right"
                    )}
                  >
                    {col.render
                      ? col.render(row[col.key], row)
                      : String(row[col.key] ?? "")}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {sortedData.length === 0 && (
        <div className="text-center py-8 text-zinc-500 text-sm">
          No data available
        </div>
      )}
    </div>
  );
}
