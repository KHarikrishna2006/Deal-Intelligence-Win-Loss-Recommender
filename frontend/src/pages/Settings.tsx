import { useQuery } from "@tanstack/react-query";
import { Database, Cpu, Brain, Users } from "lucide-react";
import { Badge, Card, Loading, SectionTitle } from "../components/ui";
import { api } from "../lib/api";

interface HealthResponse {
  status: string;
  service: string;
  environment: string;
  uptime_seconds: number;
}

interface ReadyResponse {
  status: string;
  checks: Record<string, Record<string, unknown>>;
  degraded_reasons: string[];
}

interface MemoryStatus {
  available: boolean;
  configured_url: string;
  enabled: boolean;
  version?: string | null;
  reason?: string | null;
  local_reference_count: number;
}

interface UserRow {
  id: string;
  email: string;
  full_name: string;
  role: string;
  title?: string | null;
  is_active: boolean;
  created_at: string;
}

function Check({
  icon,
  name,
  available,
  detail,
}: {
  icon: React.ReactNode;
  name: string;
  available: boolean;
  detail?: string;
}) {
  return (
    <div className="flex items-start gap-3 rounded-lg border border-line bg-surface-sunken p-3">
      <span className={available ? "text-success" : "text-warning"}>{icon}</span>
      <div className="min-w-0">
        <div className="flex items-center gap-2">
          <p className="text-sm font-medium text-ink">{name}</p>
          <Badge tone={available ? "success" : "warning"}>{available ? "OK" : "DEGRADED"}</Badge>
        </div>
        {detail ? <p className="mt-0.5 text-[11px] text-ink-faint">{detail}</p> : null}
      </div>
    </div>
  );
}

export default function Settings() {
  const health = useQuery({
    queryKey: ["health"],
    queryFn: () => api.get<HealthResponse>("/health"),
    refetchInterval: 30_000,
  });
  const ready = useQuery({
    queryKey: ["ready"],
    queryFn: () => api.get<ReadyResponse>("/ready"),
    refetchInterval: 30_000,
  });
  const memory = useQuery({
    queryKey: ["memory-status"],
    queryFn: () => api.get<MemoryStatus>("/memory/status"),
    refetchInterval: 30_000,
  });
  const users = useQuery({
    queryKey: ["users"],
    queryFn: () => api.get<UserRow[]>("/auth/users"),
  });

  if (health.isLoading || ready.isLoading) return <Loading />;

  const db = ready.data?.checks?.database ?? {};
  const llm = ready.data?.checks?.llm ?? {};
  const hind = ready.data?.checks?.hindsight ?? {};

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">System health</h1>
        <p className="text-xs text-ink-faint">
          Liveness, readiness and the state of every downstream dependency.
        </p>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4">
          <SectionTitle
            title="Application"
            subtitle={health.data ? `${health.data.service} · ${health.data.environment}` : ""}
            actions={
              <Badge tone={health.data?.status === "ok" ? "success" : "warning"}>
                {health.data?.status ?? "…"}
              </Badge>
            }
          />
          <p className="text-xs text-ink-muted">
            Uptime: {Math.round(health.data?.uptime_seconds ?? 0)}s
          </p>
          <p className="mt-1 text-[11px] text-ink-faint">
            GET /api/health · GET /api/ready
          </p>
        </div>

        <div className="card p-4 lg:col-span-2">
          <SectionTitle
            title="Dependencies"
            subtitle={
              ready.data
                ? `Overall: ${ready.data.status}${
                    ready.data.degraded_reasons.length
                      ? ` · degraded: ${ready.data.degraded_reasons.join(", ")}`
                      : ""
                  }`
                : ""
            }
          />
          <div className="space-y-2">
            <Check
              icon={<Database className="h-4 w-4" />}
              name="PostgreSQL"
              available={Boolean(db.available)}
              detail={`${db.available ? "connected" : String(db.error ?? "unavailable")}${
                db.latency_ms !== undefined ? ` · ${db.latency_ms}ms` : ""
              }`}
            />
            <Check
              icon={<Brain className="h-4 w-4" />}
              name="Hindsight memory"
              available={Boolean(hind.available)}
              detail={String(hind.reason ?? hind.configured_url ?? "Hindsight")}
            />
            <Check
              icon={<Cpu className="h-4 w-4" />}
              name="Local LLM (Ollama)"
              available={Boolean(llm.available)}
              detail={String(llm.model ?? llm.reason ?? "llama3.2:3b")}
            />
          </div>
          <div className="mt-3 rounded-lg border border-line bg-surface-sunken p-3">
            <p className="label">Graceful degradation</p>
            <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
              If Hindsight or the LLM is unreachable, every read and write path keeps working from
              PostgreSQL. Memory rows are marked FAILED and retried; recommendations fall back to
              the deterministic evidence engine and are labelled DETERMINISTIC.
            </p>
          </div>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        <div className="card p-4 lg:col-span-2">
          <SectionTitle
            title="Organisation members"
            subtitle="Role based access control is enforced on every endpoint"
            actions={<Users className="h-4 w-4 text-ink-faint" />}
          />
          <table className="w-full text-left text-xs">
            <thead>
              <tr className="border-b border-line text-[11px] uppercase tracking-wide text-ink-faint">
                <th className="pb-2">Name</th>
                <th className="pb-2">Email</th>
                <th className="pb-2">Role</th>
                <th className="pb-2">Status</th>
              </tr>
            </thead>
            <tbody>
              {(users.data ?? []).map((user) => (
                <tr key={user.id} className="border-b border-line last:border-0">
                  <td className="py-2 text-ink">{user.full_name}</td>
                  <td className="py-2 text-ink-muted">{user.email}</td>
                  <td className="py-2 text-ink-muted">{user.role.replace("_", " ")}</td>
                  <td className="py-2">
                    <Badge tone={user.is_active ? "success" : "danger"}>
                      {user.is_active ? "ACTIVE" : "INACTIVE"}
                    </Badge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>

        <Card className="p-4">
          <SectionTitle title="Memory layer" />
          <div className="space-y-2 text-xs">
            <div className="flex items-center justify-between">
              <span className="text-ink-muted">Endpoint</span>
              <span className="font-mono text-[11px]">{memory.data?.configured_url}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-ink-muted">Enabled</span>
              <Badge tone={memory.data?.enabled ? "success" : "warning"}>
                {memory.data?.enabled ? "YES" : "NO"}
              </Badge>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-ink-muted">Local references</span>
              <span>{memory.data?.local_reference_count ?? 0}</span>
            </div>
            <div className="flex items-center justify-between">
              <span className="text-ink-muted">Version</span>
              <span className="text-[10px]">{String(memory.data?.version ?? "—").slice(0, 40)}</span>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
