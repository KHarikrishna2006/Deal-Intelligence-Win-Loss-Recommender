import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, ArrowRight, CircleDot } from "lucide-react";
import { Link } from "react-router-dom";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { SectionTitle, Stat, EmptyState, Loading, Badge } from "../components/ui";
import { api } from "../lib/api";
import type { Dashboard as DashboardData } from "../lib/types";
import { compactMoney, relativeTime, stageTone, STAGE_LABEL } from "../lib/utils";

const PALETTE = ["#3b82f6", "#22c55e", "#f59e0b", "#ef4444", "#8b5cf6", "#06b6d4", "#ec4899"];

function ChartCard({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  return (
    <div className="card p-4">
      <SectionTitle title={title} subtitle={subtitle} />
      <div className="h-52">{children}</div>
    </div>
  );
}

const tooltipStyle = {
  borderRadius: 10,
  border: "1px solid rgb(var(--line))",
  background: "rgb(var(--surface-raised))",
  color: "rgb(var(--ink))",
  fontSize: 12,
};

export default function Dashboard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["dashboard"],
    queryFn: () => api.get<DashboardData>("/dashboard"),
  });

  if (isLoading) return <Loading />;
  if (error || !data)
    return (
      <EmptyState
        title="Dashboard unavailable"
        description="We could not load the analytics snapshot. Check that the API is running."
      />
    );

  const kpis = data.kpis;
  const pipeline = data.pipeline_by_stage.map((p) => ({ ...p, value: Number(p.value) }));
  const winLoss = data.win_loss.map((p) => ({ ...p, value: Number(p.value) }));

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Revenue dashboard</h1>
        <p className="text-xs text-ink-faint">
          PostgreSQL is the source of truth; Hindsight supplies the contextual memory layer.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat
          label="Open pipeline"
          value={compactMoney(kpis.pipeline_value)}
          hint={`${kpis.active_deals} active deals`}
        />
        <Stat
          label="Win rate"
          value={kpis.win_rate === null || kpis.win_rate === undefined ? "—" : `${kpis.win_rate}%`}
          hint={`${kpis.won_deals} won / ${kpis.lost_deals} lost`}
        />
        <Stat
          label="Average deal size"
          value={compactMoney(kpis.average_deal_size)}
          hint={`${kpis.closed_total} closed opportunities`}
        />
        <Stat
          label="Average sales cycle"
          value={kpis.average_sales_cycle_days ? `${kpis.average_sales_cycle_days}d` : "—"}
          hint="Closed-won opportunities"
        />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <ChartCard title="Pipeline by stage" subtitle="Open deal value per stage">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={pipeline} margin={{ left: -18, right: 8, top: 8 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
              <XAxis
                dataKey="label"
                tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }}
                tickLine={false}
                axisLine={false}
              />
              <YAxis
                tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }}
                tickLine={false}
                axisLine={false}
                tickFormatter={(v) => compactMoney(v)}
              />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => compactMoney(v)} />
              <Bar dataKey="value" radius={[6, 6, 0, 0]}>
                {pipeline.map((_, index) => (
                  <Cell key={index} fill={PALETTE[index % PALETTE.length]} />
                ))}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Win / loss distribution" subtitle="Closed opportunities">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={winLoss}
                dataKey="value"
                nameKey="label"
                innerRadius={54}
                outerRadius={82}
                paddingAngle={3}
              >
                {winLoss.map((_, index) => (
                  <Cell key={index} fill={index === 0 ? "#22c55e" : "#ef4444"} />
                ))}
              </Pie>
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Top objections" subtitle="Recorded across deals">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={data.top_objections.map((p) => ({ ...p, value: Number(p.value) }))}
              layout="vertical"
              margin={{ left: 30, right: 12 }}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <YAxis
                type="category"
                dataKey="label"
                width={120}
                tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }}
              />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" fill="#f59e0b" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </ChartCard>

        <ChartCard title="Competitor outcomes" subtitle="Wins and losses by competitor">
          <div className="space-y-2 overflow-y-auto pr-1" style={{ height: "100%" }}>
            {data.competitor_outcomes.length === 0 ? (
              <p className="text-xs text-ink-faint">No competitor data recorded yet.</p>
            ) : (
              data.competitor_outcomes.map((row, index) => {
                const rec = row as Record<string, string | number>;
                const total = Number(rec.total ?? 0) || 1;
                const won = Number(rec.won ?? 0);
                return (
                  <div key={index} className="text-xs">
                    <div className="flex items-center justify-between">
                      <span className="font-medium text-ink">{String(rec.competitor ?? rec.name)}</span>
                      <span className="text-ink-faint">
                        {won}/{total} won
                      </span>
                    </div>
                    <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-surface-sunken">
                      <div
                        className="h-full rounded-full bg-accent"
                        style={{ width: `${Math.round((won / total) * 100)}%` }}
                      />
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </ChartCard>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <SectionTitle
            title="Recent activity"
            subtitle="Latest deal events across the organisation"
            actions={
              <Link to="/pipeline" className="flex items-center gap-1 text-xs text-accent">
                Open pipeline <ArrowRight className="h-3 w-3" />
              </Link>
            }
          />
          <ul className="divide-y divide-line">
            {data.recent_activity.slice(0, 8).map((item, index) => (
              <li key={index} className="flex items-start gap-3 py-2.5">
                <CircleDot className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                <div className="min-w-0">
                  <p className="truncate text-sm text-ink">{item.title}</p>
                  {item.detail ? (
                    <p className="truncate text-xs text-ink-faint">{item.detail}</p>
                  ) : null}
                </div>
                <span className="ml-auto shrink-0 text-[11px] text-ink-faint">
                  {relativeTime(item.occurred_at)}
                </span>
              </li>
            ))}
          </ul>
        </div>

        <div className="card p-4">
          <SectionTitle title="Open pipeline" subtitle="Deal stage snapshot" />
          <div className="flex flex-wrap gap-2">
            {pipeline.map((stage) => (
              <span key={stage.label} className={`chip border ${stageTone(stage.label)}`}>
                {STAGE_LABEL[stage.label] ?? stage.label}: {stage.value}
              </span>
            ))}
          </div>
          <div className="mt-4 rounded-lg border border-warning/30 bg-warning/10 p-3 text-xs text-warning">
            <div className="flex items-start gap-2">
              <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <p className="leading-relaxed">
                Recommendations only appear where real evidence exists. Thin pipelines are reported
                honestly instead of padded with invented numbers.
              </p>
            </div>
          </div>
          <div className="mt-3 flex items-center gap-2">
            <Badge tone="accent">Evidence-first</Badge>
            <Badge tone="success">Deterministic fallback</Badge>
          </div>
        </div>
      </div>
    </div>
  );
}
