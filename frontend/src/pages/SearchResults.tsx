import { useQuery } from "@tanstack/react-query";
import { Search } from "lucide-react";
import { useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { Badge, EmptyState, Input, Loading } from "../components/ui";
import { api, queryString } from "../lib/api";
import type { SearchHit } from "../lib/types";

interface SearchResponse {
  query: string;
  hits: SearchHit[];
  counts: Record<string, number>;
  total: number;
}

export default function SearchResults() {
  const [params, setParams] = useSearchParams();
  const initial = params.get("q") ?? "";
  const [value, setValue] = useState(initial);
  const q = params.get("q") ?? "";

  const { data, isLoading, isFetching } = useQuery({
    queryKey: ["search", q],
    queryFn: () => api.get<SearchResponse>(`/search${queryString({ q, limit: 60 })}`),
    enabled: q.length > 0,
  });

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Search</h1>
        <p className="text-xs text-ink-faint">Deals, customers, interactions, objections and more.</p>
      </div>

      <form
        className="relative max-w-xl"
        onSubmit={(event) => {
          event.preventDefault();
          setParams(value.trim() ? { q: value.trim() } : {});
        }}
      >
        <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
        <Input
          className="pl-9"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          placeholder="Search everything…"
          autoFocus
        />
      </form>

      {!q ? (
        <EmptyState title="Type something to search" description="e.g. “pricing objection”, “Acme”, “lost security”." />
      ) : isLoading || isFetching ? (
        <Loading />
      ) : (data?.hits ?? []).length === 0 ? (
        <EmptyState title={`No results for “${q}”`} />
      ) : (
        <div className="space-y-4">
          <div className="flex flex-wrap gap-1.5">
            {Object.entries(data?.counts ?? {}).map(([type, count]) => (
              <span key={type} className="chip">
                {type}: {count}
              </span>
            ))}
          </div>

          <ul className="space-y-2">
            {(data?.hits ?? []).map((hit) => {
              const extra = hit.extra ?? {};
              const target =
                hit.entity_type === "deal"
                  ? `/deals/${hit.id}`
                  : hit.entity_type === "customer"
                    ? `/customers/${hit.id}`
                    : hit.entity_type === "interaction" && extra.deal_id
                      ? `/deals/${String(extra.deal_id)}`
                      : null;
              const content = (
                <div className="card p-3.5 transition hover:border-accent/50">
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex items-center gap-2">
                        <Badge tone="accent">{hit.entity_type}</Badge>
                        <p className="truncate text-sm font-medium text-ink">{hit.title}</p>
                      </div>
                      {hit.subtitle ? (
                        <p className="mt-1 line-clamp-2 text-xs text-ink-muted">{hit.subtitle}</p>
                      ) : null}
                    </div>
                    <span className="shrink-0 text-[11px] text-ink-faint">
                      {hit.score.toFixed(2)}
                    </span>
                  </div>
                </div>
              );
              return target ? (
                <li key={`${hit.entity_type}-${hit.id}`}>
                  <Link to={target} className="block">
                    {content}
                  </Link>
                </li>
              ) : (
                <li key={`${hit.entity_type}-${hit.id}`}>{content}</li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}
