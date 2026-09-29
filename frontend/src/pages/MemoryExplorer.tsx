import { useMutation, useQuery } from "@tanstack/react-query";
import { Brain, RefreshCw, Search, Sparkles } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import {
  Badge,
  Button,
  EmptyState,
  ErrorNote,
  Input,
  Loading,
  SectionTitle,
  Select,
} from "../components/ui";
import { api, queryString } from "../lib/api";
import type { MemoryStatus } from "../lib/types";
import { formatDateTime, relativeTime } from "../lib/utils";

interface ReferenceRow {
  id: string;
  deal_id?: string | null;
  kind: string;
  content: string;
  context?: string | null;
  meta?: Record<string, unknown> | null;
  tags?: string[] | null;
  sync_status: string;
  sync_error?: string | null;
  created_at: string;
}

const KINDS = [
  "ALL",
  "INTERACTION",
  "OUTCOME",
  "DEAL_CONTEXT",
  "OBJECTION",
  "COMPETITOR",
  "PRICING",
  "CUSTOMER",
];

export default function MemoryExplorer() {
  const [search, setSearch] = useState("");
  const [query, setQuery] = useState("");
  const [kind, setKind] = useState("ALL");
  const [question, setQuestion] = useState("");

  const statusQuery = useQuery({
    queryKey: ["memory-status"],
    queryFn: () => api.get<MemoryStatus>("/memory/status"),
    refetchInterval: 30_000,
  });

  const referencesQuery = useQuery({
    queryKey: ["memory-references", query, kind],
    queryFn: () =>
      api.get<{ items: ReferenceRow[]; total: number }>(
        `/memory/references${queryString({ search: query, kind: kind === "ALL" ? undefined : kind, limit: 100 })}`,
      ),
  });

  const remoteSearch = useMutation({
    mutationFn: (q: string) =>
      api.get<{
        query: string;
        local: ReferenceRow[];
        local_total: number;
        remote: { id: string; text: string; score?: number | null; tags?: string[] }[];
        remote_status: MemoryStatus;
      }>(`/memory/search${queryString({ q, use_hindsight: true })}`),
  });

  const insights = useMutation({
    mutationFn: (q: string) =>
      api.get<{ available: boolean; text: string; reason?: string | null; structured?: unknown }>(
        `/memory/insights${queryString({ query: q })}`,
      ),
  });

  const status = statusQuery.data;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight">
            <Brain className="h-5 w-5 text-accent" /> Memory explorer
          </h1>
          <p className="text-xs text-ink-faint">
            PostgreSQL stores the records; Hindsight stores the context. This page shows both.
          </p>
        </div>
        <Badge tone={status?.available ? "success" : status ? "warning" : "neutral"}>
          {status?.available ? "HINDSIGHT AVAILABLE" : status ? "HINDSIGHT UNAVAILABLE" : "CHECKING…"}
        </Badge>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <SectionTitle
            title="Memory status"
            subtitle={status?.configured_url}
            actions={
              <Button size="sm" variant="ghost" onClick={() => statusQuery.refetch()}>
                <RefreshCw className="h-3.5 w-3.5" /> Refresh
              </Button>
            }
          />
          <div className="grid gap-3 sm:grid-cols-3">
            <div>
              <p className="label">Bank</p>
              <p className="mt-1 break-all font-mono text-[11px] text-ink">
                {status?.bank_id ?? "—"}
              </p>
            </div>
            <div>
              <p className="label">Local references</p>
              <p className="mt-1 text-lg font-semibold">{status?.local_reference_count ?? 0}</p>
            </div>
            <div>
              <p className="label">Version</p>
              <p className="mt-1 text-[11px] text-ink-muted">
                {status?.version ? String(status.version).slice(0, 80) : "—"}
              </p>
            </div>
          </div>
          {status && !status.available ? (
            <div className="mt-3">
              <ErrorNote
                message={`${status.reason ?? "unavailable"} — the app keeps working from PostgreSQL and will retry.`}
              />
            </div>
          ) : null}
        </div>

        <div className="card p-4">
          <SectionTitle title="Reflect" subtitle="Ask the memory bank a question" />
          <div className="space-y-2">
            <Input
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              placeholder="What objections keep repeating?"
            />
            <Button
              className="w-full"
              disabled={insights.isPending || question.trim().length < 3}
              onClick={() => insights.mutate(question.trim())}
            >
              <Sparkles className="h-4 w-4" />
              {insights.isPending ? "Reflecting…" : "Reflect"}
            </Button>
          </div>
          {insights.data ? (
            <div className="mt-3 rounded-lg border border-line bg-surface-sunken p-3 text-xs leading-relaxed text-ink-muted">
              {insights.data.available ? (
                insights.data.text || "No insight produced."
              ) : (
                <span className="text-warning">
                  Reflection unavailable: {insights.data.reason ?? "unknown"}
                </span>
              )}
            </div>
          ) : null}
        </div>
      </div>

      <div className="card p-4">
        <SectionTitle
          title="Hybrid search"
          subtitle="Local index first, then Hindsight recall"
        />
        <form
          className="flex flex-wrap gap-2"
          onSubmit={(event) => {
            event.preventDefault();
            const q = search.trim();
            if (q) remoteSearch.mutate(q);
          }}
        >
          <div className="relative min-w-[260px] flex-1">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
            <Input
              className="pl-9"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search retained memories…"
            />
          </div>
          <Button type="submit" disabled={remoteSearch.isPending}>
            {remoteSearch.isPending ? "Searching…" : "Search memory"}
          </Button>
        </form>

        {remoteSearch.data ? (
          <div className="mt-4 grid gap-4 lg:grid-cols-2">
            <div>
              <p className="label">
                Hindsight recall ({remoteSearch.data.remote.length})
                <span className="ml-2 normal-case text-ink-faint">
                  {remoteSearch.data.remote_status.available ? "live" : "offline"}
                </span>
              </p>
              <ul className="mt-2 space-y-2">
                {remoteSearch.data.remote.length === 0 ? (
                  <li className="text-xs text-ink-faint">No memories recalled.</li>
                ) : (
                  remoteSearch.data.remote.map((hit) => (
                    <li key={hit.id} className="rounded-lg border border-line bg-surface-sunken p-2.5">
                      <p className="text-xs text-ink">{hit.text}</p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {hit.tags?.map((t) => (
                          <span key={t} className="chip">
                            {t}
                          </span>
                        ))}
                        {hit.score ? <span className="chip">{hit.score.toFixed(2)}</span> : null}
                      </div>
                    </li>
                  ))
                )}
              </ul>
            </div>
            <div>
              <p className="label">Local index ({remoteSearch.data.local_total})</p>
              <ul className="mt-2 space-y-2">
                {remoteSearch.data.local.length === 0 ? (
                  <li className="text-xs text-ink-faint">Nothing in the local index.</li>
                ) : (
                  remoteSearch.data.local.map((row) => (
                    <li key={row.id} className="rounded-lg border border-line p-2.5">
                      <div className="flex items-center justify-between gap-2">
                        <span className="chip">{row.kind}</span>
                        <span
                          className={`text-[10px] ${
                            row.sync_status === "SYNCED" ? "text-success" : "text-danger"
                          }`}
                        >
                          {row.sync_status}
                        </span>
                      </div>
                      <p className="mt-1 text-[11px] text-ink-muted">{row.content.slice(0, 220)}</p>
                    </li>
                  ))
                )}
              </ul>
            </div>
          </div>
        ) : null}
      </div>

      <div className="card p-4">
        <SectionTitle
          title="Retained memories"
          subtitle={`${referencesQuery.data?.total ?? 0} references`}
        />
        <div className="mb-3 flex flex-wrap gap-2">
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Filter by content…"
            className="h-9 w-64"
          />
          <Select value={kind} onChange={(e) => setKind(e.target.value)} className="h-9 w-52">
            {KINDS.map((k) => (
              <option key={k} value={k}>
                {k === "ALL" ? "All kinds" : k.replace(/_/g, " ")}
              </option>
            ))}
          </Select>
        </div>

        {referencesQuery.isLoading ? (
          <Loading />
        ) : (referencesQuery.data?.items ?? []).length === 0 ? (
          <EmptyState
            title="No memories retained yet"
            description="Log an interaction or record an outcome — the app writes a distilled summary into Hindsight and keeps a local index row here."
          />
        ) : (
          <ul className="space-y-2">
            {(referencesQuery.data?.items ?? []).map((row) => (
              <li key={row.id} className="rounded-lg border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div className="flex flex-wrap gap-1.5">
                    <span className="chip">{row.kind}</span>
                    {row.tags?.map((t) => (
                      <span key={t} className="chip">
                        {t}
                      </span>
                    ))}
                  </div>
                  <span
                    className={`text-[10px] ${
                      row.sync_status === "SYNCED" ? "text-success" : "text-danger"
                    }`}
                  >
                    {row.sync_status}
                    {row.sync_error ? ` · ${row.sync_error}` : ""}
                  </span>
                </div>
                <p className="mt-2 whitespace-pre-wrap text-xs leading-relaxed text-ink-muted">
                  {row.content}
                </p>
                <div className="mt-2 flex flex-wrap items-center justify-between gap-2 text-[11px] text-ink-faint">
                  <span>
                    {formatDateTime(row.created_at)} · {relativeTime(row.created_at)}
                  </span>
                  {row.deal_id ? (
                    <Link to={`/deals/${row.deal_id}`} className="text-accent">
                      Open deal →
                    </Link>
                  ) : null}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
