import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, ArrowUpRight, ThumbsDown, ThumbsUp } from "lucide-react";
import { Link } from "react-router-dom";
import { Badge, EmptyState, Loading, SectionTitle, Tabs } from "../components/ui";
import { api, queryString } from "../lib/api";
import type { Paged, Recommendation } from "../lib/types";
import { formatDateTime } from "../lib/utils";
import { useState } from "react";

export default function Recommendations() {
  const qc = useQueryClient();
  const [kind, setKind] = useState("ALL");

  const { data, isLoading } = useQuery({
    queryKey: ["recommendations", kind],
    queryFn: () =>
      api.get<Paged<Recommendation>>(
        `/recommendations${queryString({ kind: kind === "ALL" ? undefined : kind, limit: 100 })}`,
      ),
  });

  const feedback = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) =>
      api.post(`/recommendations/${id}/feedback`, { feedback: value }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["recommendations"] }),
  });

  const items = data?.items ?? [];

  return (
    <div className="space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Recommendations</h1>
        <p className="text-xs text-ink-faint">
          Evidence-backed next actions, risks and insights across every deal.
        </p>
      </div>

      <Tabs
        tabs={[
          { id: "ALL", label: "All" },
          { id: "NEXT_ACTION", label: "Next actions" },
          { id: "RISK", label: "Risks" },
          { id: "INSIGHT", label: "Insights" },
        ]}
        active={kind}
        onChange={setKind}
      />

      {isLoading ? (
        <Loading />
      ) : items.length === 0 ? (
        <EmptyState
          title="No recommendations yet"
          description="Open a deal and run the analysis. The engine only produces recommendations it can back with real evidence."
          action={<Link to="/pipeline" className="text-xs text-accent">Open pipeline →</Link>}
        />
      ) : (
        <div className="space-y-4">
          {items.map((rec) => (
            <div key={rec.id} className="card p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <Badge
                      tone={
                        rec.evidence_level === "EVIDENCE_BASED"
                          ? "success"
                          : rec.evidence_level === "INSUFFICIENT_DATA"
                            ? "warning"
                            : "accent"
                      }
                    >
                      {rec.evidence_level.replace(/_/g, " ")}
                    </Badge>
                    <Badge>{rec.kind.replace(/_/g, " ")}</Badge>
                    <Badge tone={rec.source === "LLM" ? "accent" : "neutral"}>{rec.source}</Badge>
                    {rec.risk_level ? <Badge tone="danger">{rec.risk_level} risk</Badge> : null}
                  </div>
                  <h2 className="mt-2 text-sm font-semibold text-ink">{rec.title}</h2>
                  <p className="mt-1 max-w-3xl text-xs leading-relaxed text-ink-muted">
                    {rec.rationale}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-3">
                  <span className="text-[11px] text-ink-faint">{formatDateTime(rec.created_at)}</span>
                  <div className="flex gap-1">
                    <button
                      onClick={() => feedback.mutate({ id: rec.id, value: "USEFUL" })}
                      className="rounded-md border border-line p-1.5 text-ink-faint hover:text-success"
                      title="Useful"
                    >
                      <ThumbsUp className="h-3.5 w-3.5" />
                    </button>
                    <button
                      onClick={() => feedback.mutate({ id: rec.id, value: "NOT_USEFUL" })}
                      className="rounded-md border border-line p-1.5 text-ink-faint hover:text-danger"
                      title="Not useful"
                    >
                      <ThumbsDown className="h-3.5 w-3.5" />
                    </button>
                  </div>
                </div>
              </div>

              {Array.isArray(rec.actions) && rec.actions.length ? (
                <ul className="mt-3 grid gap-2 sm:grid-cols-2">
                  {(rec.actions as { title?: string; rationale?: string }[]).map((action, index) => (
                    <li key={index} className="rounded-lg border border-line bg-surface-sunken p-2.5">
                      <p className="text-xs font-medium text-ink">{action.title ?? `Action ${index + 1}`}</p>
                      {action.rationale ? (
                        <p className="mt-0.5 text-[11px] text-ink-muted">{action.rationale}</p>
                      ) : null}
                    </li>
                  ))}
                </ul>
              ) : null}

              {rec.evidence?.length ? (
                <div className="mt-3">
                  <p className="label">Evidence</p>
                  <ul className="mt-1.5 space-y-1">
                    {rec.evidence.map((item, index) => (
                      <li key={index} className="text-[11px] text-ink-muted">
                        <span className="font-medium text-ink">{item.deal_name ?? "Similar deal"}</span>{" "}
                        — {item.why ?? item.text ?? ""}
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}

              {rec.unknowns?.length ? (
                <div className="mt-3 flex gap-2 rounded-lg border border-warning/30 bg-warning/10 p-2.5 text-[11px] text-warning">
                  <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                  <ul className="space-y-0.5">
                    {rec.unknowns.map((u, i) => (
                      <li key={i}>{u}</li>
                    ))}
                  </ul>
                </div>
              ) : null}

              <div className="mt-3 flex items-center justify-between border-t border-line pt-3">
                <Link
                  to={`/deals/${rec.deal_id}`}
                  className="flex items-center gap-1 text-[11px] text-accent"
                >
                  Open deal <ArrowUpRight className="h-3 w-3" />
                </Link>
                <div className="flex items-center gap-2 text-[11px] text-ink-faint">
                  {rec.feedback?.length ? <span>Feedback recorded</span> : null}
                  {rec.model ? <span className="font-mono">{rec.model}</span> : null}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="card p-4">
        <SectionTitle title="How recommendations are produced" />
        <ol className="list-inside list-decimal space-y-1 text-xs text-ink-muted">
          <li>Pull structured evidence from PostgreSQL (stage, objections, competitors, pricing, outcomes).</li>
          <li>Recall contextual memories from Hindsight for the organisation's bank.</li>
          <li>Ask the local LLM for a ranked plan — or fall back to a deterministic evidence engine.</li>
          <li>Validate every cited reference against the database; drop anything unverifiable.</li>
          <li>If evidence is thin, return “Insufficient historical data” rather than a confident guess.</li>
        </ol>
      </div>
    </div>
  );
}
