import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Badge, EmptyState, Loading, SectionTitle, Tabs } from "../components/ui";
import { api, queryString } from "../lib/api";
import type { Customer, Deal, Interaction, MemoryReference } from "../lib/types";
import { compactMoney, formatDateTime, money, stageTone, STAGE_LABEL } from "../lib/utils";
import { useState } from "react";

interface CustomerDetailPayload extends Customer {
  active_deals: { id: string; name: string; stage: string; amount: number; currency: string }[];
  past_deals: {
    id: string;
    name: string;
    stage: string;
    amount: number;
    currency: string;
    outcome?: string | null;
    loss_reason?: string | null;
    win_reason?: string | null;
  }[];
  interaction_count: number;
  objections: { label: string; total: number; open: number }[];
  competitors: { name: string; total: number }[];
  pricing_history: {
    interaction_id: string;
    occurred_at: string;
    amount: number | null;
    currency: string | null;
    type: string;
  }[];
  recommendations: {
    id: string;
    deal_id: string;
    title: string;
    evidence_level: string;
    created_at: string;
  }[];
  memory_timeline: {
    source: string;
    occurred_at: string;
    title: string;
    detail?: string | null;
    kind: string;
  }[];
}

const TABS = [
  { id: "deals", label: "Deals" },
  { id: "activity", label: "Activity" },
  { id: "objections", label: "Objections & competitors" },
  { id: "pricing", label: "Pricing history" },
  { id: "memory", label: "Memory" },
];

export default function CustomerDetail() {
  const { customerId = "" } = useParams();
  const [tab, setTab] = useState("deals");

  const { data, isLoading } = useQuery({
    queryKey: ["customer", customerId],
    queryFn: () => api.get<CustomerDetailPayload>(`/customers/${customerId}`),
    enabled: Boolean(customerId),
  });

  const interactionsQuery = useQuery({
    queryKey: ["customer", customerId, "interactions"],
    queryFn: () =>
      api.get<{ items: Interaction[]; total: number }>(
        `/interactions${queryString({ customer_id: customerId, limit: 100 })}`,
      ),
    enabled: tab === "activity" && Boolean(customerId),
  });

  if (isLoading) return <Loading />;
  if (!data) return <EmptyState title="Customer not found" />;

  return (
    <div className="space-y-5">
      <div>
        <Link to="/customers" className="text-xs text-ink-faint">
          ← Customers
        </Link>
        <div className="mt-1 flex flex-wrap items-end justify-between gap-3">
          <div>
            <h1 className="text-xl font-semibold tracking-tight">{data.name}</h1>
            <p className="text-xs text-ink-faint">
              {data.industry || "Industry unknown"} · {data.segment || "Segment unknown"} ·{" "}
              {data.region || "Region unknown"}
              {data.employee_count ? ` · ${data.employee_count} employees` : ""}
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <span className="chip">{data.active_deals.length} active</span>
            <span className="chip">{data.past_deals.length} past</span>
            <span className="chip">{data.interaction_count} interactions</span>
          </div>
        </div>
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "deals" ? (
        <div className="space-y-5">
          <div>
            <SectionTitle title="Active deals" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {data.active_deals.map((deal) => (
                <Link key={deal.id} to={`/deals/${deal.id}`} className="card p-4 hover:border-accent/50">
                  <p className="truncate text-sm font-medium text-ink">{deal.name}</p>
                  <div className="mt-2 flex items-center justify-between">
                    <span className={`chip border ${stageTone(deal.stage)}`}>
                      {STAGE_LABEL[deal.stage] ?? deal.stage}
                    </span>
                    <span className="text-sm font-semibold">{compactMoney(deal.amount, deal.currency)}</span>
                  </div>
                </Link>
              ))}
              {data.active_deals.length === 0 ? (
                <EmptyState title="No active deals" description="All opportunities for this account are closed." />
              ) : null}
            </div>
          </div>

          <div>
            <SectionTitle title="Past deals" />
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
              {data.past_deals.map((deal) => (
                <Link key={deal.id} to={`/deals/${deal.id}`} className="card p-4 hover:border-accent/50">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-xs font-medium text-ink">{deal.name}</p>
                    <Badge tone={deal.outcome === "WON" ? "success" : "danger"}>{deal.outcome}</Badge>
                  </div>
                  <p className="mt-1 text-[11px] text-ink-faint">{compactMoney(deal.amount, deal.currency)}</p>
                  <p className="mt-2 line-clamp-2 text-[11px] text-ink-muted">
                    {deal.win_reason || deal.loss_reason || "No reason recorded."}
                  </p>
                </Link>
              ))}
              {data.past_deals.length === 0 ? <EmptyState title="No closed deals" /> : null}
            </div>
          </div>
        </div>
      ) : null}

      {tab === "activity" ? (
        interactionsQuery.isLoading ? (
          <Loading />
        ) : (interactionsQuery.data?.items ?? []).length === 0 ? (
          <EmptyState title="No interactions recorded for this account" />
        ) : (
          <div className="space-y-3">
            {(interactionsQuery.data?.items ?? []).map((item) => (
              <div key={item.id} className="card p-4">
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <p className="text-sm font-medium text-ink">{item.title || item.interaction_type}</p>
                    <p className="text-[11px] text-ink-faint">
                      {item.interaction_type} · {formatDateTime(item.occurred_at)}
                    </p>
                  </div>
                  <Link to={`/deals/${item.deal_id}`} className="text-[11px] text-accent">
                    View deal
                  </Link>
                </div>
                <p className="mt-2 text-xs leading-relaxed text-ink-muted">{item.body}</p>
              </div>
            ))}
          </div>
        )
      ) : null}

      {tab === "objections" ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <div className="card p-4">
            <SectionTitle title="Objections" subtitle="Across all deals with this account" />
            <ul className="space-y-2">
              {data.objections.length ? (
                data.objections.map((o) => (
                  <li key={o.label} className="flex items-center justify-between gap-2 text-xs">
                    <span className="text-ink">{o.label}</span>
                    <span className="flex gap-1.5">
                      <Badge tone={o.open ? "warning" : "success"}>{o.open} open</Badge>
                      <Badge>{o.total} total</Badge>
                    </span>
                  </li>
                ))
              ) : (
                <p className="text-xs text-ink-faint">No objections recorded.</p>
              )}
            </ul>
          </div>
          <div className="card p-4">
            <SectionTitle title="Competitors" />
            <ul className="space-y-2">
              {data.competitors.length ? (
                data.competitors.map((c) => (
                  <li key={c.name} className="flex items-center justify-between gap-2 text-xs">
                    <span className="text-ink">{c.name}</span>
                    <Badge>{c.total} deals</Badge>
                  </li>
                ))
              ) : (
                <p className="text-xs text-ink-faint">No competitors recorded.</p>
              )}
            </ul>
          </div>
        </div>
      ) : null}

      {tab === "pricing" ? (
        <div className="card p-4">
          <SectionTitle
            title="Pricing history"
            subtitle="Prices captured in interaction records"
          />
          {data.pricing_history.length === 0 ? (
            <EmptyState title="No pricing recorded yet" />
          ) : (
            <div className="h-64">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart
                  data={data.pricing_history.map((p) => ({
                    label: formatDateTime(p.occurred_at),
                    value: Number(p.amount || 0),
                  }))}
                  margin={{ left: -10, top: 8 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
                  <XAxis dataKey="label" tick={{ fontSize: 9, fill: "rgb(var(--ink-faint))" }} />
                  <YAxis tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} tickFormatter={(v) => compactMoney(v)} />
                  <Tooltip
                    contentStyle={{
                      borderRadius: 10,
                      border: "1px solid rgb(var(--line))",
                      background: "rgb(var(--surface-raised))",
                      fontSize: 12,
                    }}
                    formatter={(v: number) => money(v)}
                  />
                  <Bar dataKey="value" fill="#3b82f6" radius={[6, 6, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </div>
      ) : null}

      {tab === "memory" ? (
        <div className="card p-4">
          <SectionTitle
            title="Account memory timeline"
            subtitle="Merged insights retained in Hindsight for this customer's deals"
          />
          {data.memory_timeline.length === 0 ? (
            <EmptyState
              title="No memory retained yet"
              description="Memories are written when interactions and outcomes are recorded."
            />
          ) : (
            <ol className="relative ml-3 space-y-3 border-l border-line">
              {data.memory_timeline.map((item, index) => (
                <li key={index} className="pl-4">
                  <span
                    className={`absolute -left-1.5 mt-1.5 h-2.5 w-2.5 rounded-full border-2 ${
                      item.source === "memory" ? "border-accent bg-accent" : "border-line bg-surface-raised"
                    }`}
                  />
                  <p className="text-xs font-medium text-ink">{item.title}</p>
                  <p className="text-[11px] text-ink-faint">
                    {formatDateTime(item.occurred_at)} · {item.kind} · {item.source}
                  </p>
                  {item.detail ? <p className="mt-1 text-[11px] text-ink-muted">{item.detail}</p> : null}
                </li>
              ))}
            </ol>
          )}
        </div>
      ) : null}
    </div>
  );
}
