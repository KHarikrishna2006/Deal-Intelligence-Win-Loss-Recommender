import { useQuery } from "@tanstack/react-query";
import { Building2, Calendar, MessageSquare } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, EmptyState, Loading } from "../components/ui";
import { api, queryString } from "../lib/api";
import type { Deal, Paged } from "../lib/types";
import { STAGES, STAGE_LABEL, compactMoney, formatDate, stageTone } from "../lib/utils";

export default function Pipeline() {
  const { data, isLoading } = useQuery({
    queryKey: ["deals", "all"],
    queryFn: () => api.get<Paged<Deal>>(`/deals${queryString({ limit: 200, sort: "amount" })}`),
  });

  if (isLoading) return <Loading label="Loading pipeline…" />;

  const deals = data?.items ?? [];
  const open = deals.filter((d) => d.status === "OPEN");
  const closed = deals.filter((d) => d.status !== "OPEN");

  return (
    <div className="space-y-6">
      <div className="flex items-end justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Pipeline</h1>
          <p className="text-xs text-ink-faint">
            {open.length} open · {closed.length} closed opportunities
          </p>
        </div>
        <Link to="/" className="text-xs text-accent">
          Back to dashboard
        </Link>
      </div>

      <div className="grid gap-3 lg:grid-cols-7">
        {STAGES.map((stage) => {
          const items = open.filter((d) => d.stage === stage);
          const total = items.reduce((sum, d) => sum + Number(d.amount || 0), 0);
          return (
            <div key={stage} className="min-w-0">
              <div className="mb-2 flex items-center justify-between gap-1">
                <span className={`chip border ${stageTone(stage)}`}>
                  {STAGE_LABEL[stage]}
                </span>
                <span className="text-[10px] text-ink-faint">{items.length}</span>
              </div>
              <p className="mb-2 text-[11px] text-ink-faint">{compactMoney(total)}</p>
              <div className="space-y-2">
                {items.map((deal) => (
                  <Link
                    key={deal.id}
                    to={`/deals/${deal.id}`}
                    className="block rounded-lg border border-line bg-surface-raised p-3 transition hover:border-accent/50"
                  >
                    <p className="truncate text-xs font-medium text-ink">{deal.name}</p>
                    <p className="mt-1 truncate text-[11px] text-ink-faint">
                      <Building2 className="mr-1 inline h-3 w-3" />
                      {deal.customer_name}
                    </p>
                    <div className="mt-2 flex items-center justify-between">
                      <span className="text-[11px] font-semibold text-ink">
                        {compactMoney(deal.amount, deal.currency)}
                      </span>
                      <span className="text-[10px] text-ink-faint">{deal.probability}%</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-1">
                      {deal.competitor_names?.slice(0, 2).map((name) => (
                        <span key={name} className="chip">
                          {name}
                        </span>
                      ))}
                      {deal.objection_labels && deal.objection_labels.length > 0 ? (
                        <span className="chip text-warning">{deal.objection_labels.length} open</span>
                      ) : null}
                    </div>
                  </Link>
                ))}
                {items.length === 0 ? (
                  <div className="rounded-lg border border-dashed border-line px-3 py-6 text-center text-[11px] text-ink-faint">
                    No deals
                  </div>
                ) : null}
              </div>
            </div>
          );
        })}
      </div>

      <div>
        <h2 className="mb-3 text-sm font-semibold">Recently closed</h2>
        {closed.length === 0 ? (
          <EmptyState
            title="No closed opportunities yet"
            description="Record a win or loss from a deal page to start building evidence."
          />
        ) : (
          <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
            {closed
              .slice()
              .sort((a, b) => (b.updated_at ?? "").localeCompare(a.updated_at ?? ""))
              .slice(0, 12)
              .map((deal) => (
                <Link
                  key={deal.id}
                  to={`/deals/${deal.id}`}
                  className="card p-3.5 transition hover:border-accent/50"
                >
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-xs font-medium text-ink">{deal.name}</p>
                    <Badge tone={deal.outcome === "WON" ? "success" : "danger"}>
                      {deal.outcome}
                    </Badge>
                  </div>
                  <p className="mt-1 truncate text-[11px] text-ink-faint">{deal.customer_name}</p>
                  <div className="mt-2 flex items-center justify-between text-[11px] text-ink-faint">
                    <span>{compactMoney(deal.amount, deal.currency)}</span>
                    <span className="flex items-center gap-1">
                      <Calendar className="h-3 w-3" />
                      {formatDate(deal.expected_close_date)}
                    </span>
                  </div>
                  <div className="mt-2 flex items-center gap-2 text-[11px] text-ink-faint">
                    <MessageSquare className="h-3 w-3" />
                    {deal.interaction_count ?? 0} interactions
                  </div>
                </Link>
              ))}
          </div>
        )}
      </div>
    </div>
  );
}
