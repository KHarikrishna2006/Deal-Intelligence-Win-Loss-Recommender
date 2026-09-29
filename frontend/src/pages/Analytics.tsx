import { useQuery } from "@tanstack/react-query";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { EmptyState, Loading, Stat } from "../components/ui";
import { api } from "../lib/api";
import type { WinLoss } from "../lib/types";
import { compactMoney } from "../lib/utils";

const tooltipStyle = {
  borderRadius: 10,
  border: "1px solid rgb(var(--line))",
  background: "rgb(var(--surface-raised))",
  color: "rgb(var(--ink))",
  fontSize: 12,
};

function Panel({
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
      <h2 className="text-sm font-semibold text-ink">{title}</h2>
      {subtitle ? <p className="mb-3 text-[11px] text-ink-faint">{subtitle}</p> : (
        <div className="mb-3" />
      )}
      <div className="h-56">{children}</div>
    </div>
  );
}

export default function Analytics() {
  const { data, isLoading } = useQuery({
    queryKey: ["win-loss"],
    queryFn: () => api.get<WinLoss>("/analytics/win-loss"),
  });

  if (isLoading) return <Loading label="Computing win/loss analysis…" />;
  if (!data) return <EmptyState title="Win/loss analysis unavailable" />;

  if (!data.sufficient_data) {
    return (
      <div className="space-y-5">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Win / loss analysis</h1>
        </div>
        <EmptyState
          title="Insufficient historical data"
          description={
            data.insufficient_reason ??
            "There are not enough closed opportunities yet to produce a trustworthy win/loss breakdown."
          }
        />
        <div className="card p-4">
          <p className="label">Data quality</p>
          <pre className="mt-2 overflow-x-auto text-[11px] text-ink-muted">
            {JSON.stringify(data.data_quality, null, 2)}
          </pre>
        </div>
      </div>
    );
  }

  const kpis = data.kpis;
  const objectionData = data.common_objections.map((p) => ({ ...p, value: Number(p.value) }));
  const competitorData = data.common_competitors.map((p) => ({ ...p, value: Number(p.value) }));
  const stageData = data.stage_failure_rates.map((p) => ({ ...p, value: Number(p.value) }));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Win / loss analysis</h1>
        <p className="text-xs text-ink-faint">
          Built strictly from closed opportunities in PostgreSQL.
        </p>
      </div>

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Win rate" value={`${kpis.win_rate ?? 0}%`} hint={`${kpis.closed_total} closed`} />
        <Stat label="Won" value={kpis.won_deals} hint="Closed-won opportunities" />
        <Stat label="Lost" value={kpis.lost_deals} hint="Closed-lost opportunities" />
        <Stat label="Average deal size" value={compactMoney(kpis.average_deal_size)} />
        <Stat
          label="Average sales cycle"
          value={kpis.average_sales_cycle_days ? `${kpis.average_sales_cycle_days}d` : "—"}
        />
        <Stat label="Pricing-related losses" value={data.pricing_related_losses} />
        <Stat label="Competitor-related losses" value={data.competitor_related_losses} />
        <Stat label="Open pipeline value" value={compactMoney(kpis.pipeline_value)} />
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Panel title="Win / loss distribution" subtitle="Closed opportunities">
          <ResponsiveContainer width="100%" height="100%">
            <PieChart>
              <Pie
                data={data.win_loss_distribution.map((p) => ({ ...p, value: Number(p.value) }))}
                dataKey="value"
                nameKey="label"
                innerRadius={55}
                outerRadius={85}
                paddingAngle={3}
              >
                {data.win_loss_distribution.map((_, i) => (
                  <Cell key={i} fill={i === 0 ? "#22c55e" : "#ef4444"} />
                ))}
              </Pie>
              <Legend wrapperStyle={{ fontSize: 11 }} />
              <Tooltip contentStyle={tooltipStyle} />
            </PieChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Common objections" subtitle="Frequency across all deals">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={objectionData} layout="vertical" margin={{ left: 40, right: 12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <YAxis type="category" dataKey="label" width={140} tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" fill="#f59e0b" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Common competitors" subtitle="How often each appears">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={competitorData} margin={{ left: -15 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <YAxis tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" fill="#8b5cf6" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Stage failure rate" subtitle="Share of deals lost after reaching each stage">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={stageData} margin={{ left: -15 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" vertical={false} />
              <XAxis dataKey="label" tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <YAxis tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <Tooltip contentStyle={tooltipStyle} formatter={(v: number) => `${v}%`} />
              <Bar dataKey="value" fill="#ef4444" radius={[6, 6, 0, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Loss reasons" subtitle="What the team recorded when deals were lost">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.loss_reasons.map((p) => ({ ...p, value: Number(p.value) }))} layout="vertical" margin={{ left: 40, right: 12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <YAxis type="category" dataKey="label" width={150} tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" fill="#ef4444" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>

        <Panel title="Win reasons" subtitle="What the team recorded when deals were won">
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={data.win_reasons.map((p) => ({ ...p, value: Number(p.value) }))} layout="vertical" margin={{ left: 40, right: 12 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--line))" horizontal={false} />
              <XAxis type="number" tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <YAxis type="category" dataKey="label" width={150} tick={{ fontSize: 10, fill: "rgb(var(--ink-faint))" }} />
              <Tooltip contentStyle={tooltipStyle} />
              <Bar dataKey="value" fill="#22c55e" radius={[0, 6, 6, 0]} />
            </BarChart>
          </ResponsiveContainer>
        </Panel>
      </div>

      <div className="card p-4">
        <h2 className="text-sm font-semibold text-ink">Data quality</h2>
        <pre className="mt-2 overflow-x-auto text-[11px] text-ink-muted">
          {JSON.stringify(data.data_quality, null, 2)}
        </pre>
      </div>
    </div>
  );
}
