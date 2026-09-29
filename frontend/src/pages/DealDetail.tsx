import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  Building2,
  Calendar,
  CheckCircle2,
  Clock,
  Lightbulb,
  MessageSquare,
  Send,
  Sparkles,
  ThumbsDown,
  ThumbsUp,
  Zap,
} from "lucide-react";
import { useMemo, useState } from "react";
import { Link, useParams } from "react-router-dom";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorNote,
  Field,
  Input,
  Loading,
  Modal,
  SectionTitle,
  Select,
  Stat,
  Tabs,
} from "../components/ui";
import { api } from "../lib/api";
import { useAuth } from "../lib/auth";
import type { Deal, Interaction, MemoryStatus, Recommendation, TimelineItem } from "../lib/types";
import {
  STAGE_LABEL,
  compactMoney,
  evidenceTone,
  formatDate,
  formatDateTime,
  money,
  relativeTime,
  stageTone,
} from "../lib/utils";

interface DealDetail extends Deal {
  competitors?: { id: string; name: string; strength?: string | null }[];
  objections?: {
    id: string;
    label: string;
    category?: string | null;
    status: string;
    raised_at?: string | null;
    resolution?: string | null;
  }[];
  contacts?: { id: string; full_name: string; title?: string | null }[];
}

interface AnalyzeResult {
  recommendation: Recommendation;
  similar_deals: Record<string, unknown>[];
  risks: Record<string, unknown>[];
  memory_hits: Record<string, unknown>[];
  memory_status: MemoryStatus;
  llm_status: Record<string, unknown>;
  method: string;
  warnings: string[];
}

interface CopilotResult {
  answer: string;
  citations: { id?: string; text?: string; source?: string; title?: string }[];
  tool_trace: { name?: string; detail?: string }[];
  available: boolean;
  unavailable_reason?: string | null;
  model?: string | null;
}

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "timeline", label: "Timeline" },
  { id: "interactions", label: "Interactions" },
  { id: "recommendations", label: "Recommendations" },
  { id: "copilot", label: "Copilot" },
  { id: "memory", label: "Memory" },
];

export default function DealDetail() {
  const { dealId = "" } = useParams();
  const qc = useQueryClient();
  const { session } = useAuth();
  const [tab, setTab] = useState("overview");
  const [analysis, setAnalysis] = useState<AnalyzeResult | null>(null);
  const [outcomeOpen, setOutcomeOpen] = useState(false);
  const [interactionOpen, setInteractionOpen] = useState(false);
  const [copilotInput, setCopilotInput] = useState("");
  const [copilotLog, setCopilotLog] = useState<
    { role: "user" | "assistant"; content: string; citations?: CopilotResult["citations"]; unavailable?: string | null }[]
  >([]);
  const [formError, setFormError] = useState<string | null>(null);

  const dealQuery = useQuery({
    queryKey: ["deal", dealId],
    queryFn: () => api.get<DealDetail>(`/deals/${dealId}`),
    enabled: Boolean(dealId),
  });

  const timelineQuery = useQuery({
    queryKey: ["deal", dealId, "timeline"],
    queryFn: () => api.get<TimelineItem[]>(`/deals/${dealId}/timeline`),
    enabled: Boolean(dealId) && tab === "timeline",
  });

  const interactionsQuery = useQuery({
    queryKey: ["deal", dealId, "interactions"],
    queryFn: () => api.get<{ items: Interaction[]; total: number }>(`/deals/${dealId}/interactions`),
    enabled: Boolean(dealId) && tab === "interactions",
  });

  const recommendationsQuery = useQuery({
    queryKey: ["deal", dealId, "recommendations"],
    queryFn: () => api.get<{ items: Recommendation[]; total: number }>(
      `/deals/${dealId}/recommendations`,
    ),
    enabled: Boolean(dealId) && tab === "recommendations",
  });

  const memoryQuery = useQuery({
    queryKey: ["deal", dealId, "memory"],
    queryFn: () =>
      api.get<{
        status: MemoryStatus;
        references: Record<string, unknown>[];
        total: number;
        recalled: { id: string; text: string; score?: number | null; tags?: string[] }[];
        related: { id: string; text: string; score?: number | null; tags?: string[] }[];
        related_count: number;
        recall_status: MemoryStatus;
      }>(`/deals/${dealId}/memory`),
    enabled: Boolean(dealId) && tab === "memory",
  });

  const analyze = useMutation({
    mutationFn: () => api.post<AnalyzeResult>(`/deals/${dealId}/analyze?regenerate=true`),
    onSuccess: (result) => {
      setAnalysis(result);
      void qc.invalidateQueries({ queryKey: ["deal", dealId, "recommendations"] });
      setTab("recommendations");
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Analysis failed."),
  });

  const feedback = useMutation({
    mutationFn: ({ id, value }: { id: string; value: string }) =>
      api.post(`/recommendations/${id}/feedback`, { feedback: value }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["deal", dealId, "recommendations"] }),
  });

  const askCopilot = useMutation({
    mutationFn: (question: string) =>
      api.post<CopilotResult>(`/deals/${dealId}/copilot`, { question }),
    onSuccess: (result, question) => {
      setCopilotLog((prev) => [
        ...prev,
        { role: "user", content: question },
        {
          role: "assistant",
          content: result.answer,
          citations: result.citations,
          unavailable: result.unavailable_reason,
        },
      ]);
      setCopilotInput("");
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Copilot failed."),
  });

  const addInteraction = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post<Interaction>(`/deals/${dealId}/interactions`, payload),
    onSuccess: () => {
      setInteractionOpen(false);
      void qc.invalidateQueries({ queryKey: ["deal", dealId] });
      void qc.invalidateQueries({ queryKey: ["deal", dealId, "interactions"] });
      void qc.invalidateQueries({ queryKey: ["deal", dealId, "timeline"] });
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Could not save."),
  });

  const recordOutcome = useMutation({
    mutationFn: (payload: Record<string, unknown>) =>
      api.post(`/deals/${dealId}/outcome`, payload),
    onSuccess: () => {
      setOutcomeOpen(false);
      void qc.invalidateQueries({ queryKey: ["deal", dealId] });
      void qc.invalidateQueries({ queryKey: ["deal", dealId, "timeline"] });
      void qc.invalidateQueries({ queryKey: ["dashboard"] });
    },
    onError: (err) => setFormError(err instanceof Error ? err.message : "Could not save."),
  });

  const deal = dealQuery.data;

  if (dealQuery.isLoading) return <Loading label="Loading deal…" />;
  if (!deal)
    return (
      <EmptyState
        title="Deal not found"
        description="It may have been archived, or you may not have access to it."
        action={<Link to="/pipeline" className="text-xs text-accent">Back to pipeline</Link>}
      />
    );

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div className="min-w-0">
          <Link to="/pipeline" className="text-xs text-ink-faint">
            ← Pipeline
          </Link>
          <h1 className="mt-1 truncate text-xl font-semibold tracking-tight">{deal.name}</h1>
          <div className="mt-2 flex flex-wrap items-center gap-2 text-xs text-ink-muted">
            <span className={`chip border ${stageTone(deal.stage)}`}>
              {STAGE_LABEL[deal.stage] ?? deal.stage}
            </span>
            <span className="flex items-center gap-1">
              <Building2 className="h-3.5 w-3.5" />
              <Link to={`/customers/${deal.customer_id}`} className="hover:text-accent">
                {deal.customer_name}
              </Link>
            </span>
            <span className="flex items-center gap-1">
              <Calendar className="h-3.5 w-3.5" />
              {formatDate(deal.expected_close_date)}
            </span>
            <span className="flex items-center gap-1">
              <Clock className="h-3.5 w-3.5" />
              {deal.probability}% probability
            </span>
            {deal.outcome ? (
              <Badge tone={deal.outcome === "WON" ? "success" : "danger"}>{deal.outcome}</Badge>
            ) : null}
          </div>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <div className="rounded-lg border border-line bg-surface-raised px-4 py-2 text-right">
            <p className="label">Value</p>
            <p className="text-lg font-semibold">{money(deal.amount, deal.currency)}</p>
          </div>
          <Button variant="secondary" onClick={() => setInteractionOpen(true)}>
            <MessageSquare className="h-4 w-4" /> Log interaction
          </Button>
          <Button variant="subtle" onClick={() => analyze.mutate()} disabled={analyze.isPending}>
            <Sparkles className="h-4 w-4" />
            {analyze.isPending ? "Analyzing…" : "Analyze deal"}
          </Button>
          {!deal.outcome ? (
            <Button variant="secondary" onClick={() => setOutcomeOpen(true)}>
              Record outcome
            </Button>
          ) : null}
        </div>
      </div>

      {formError ? <ErrorNote message={formError} /> : null}

      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <Stat label="Stage" value={STAGE_LABEL[deal.stage] ?? deal.stage} hint={deal.status} />
        <Stat
          label="Interactions"
          value={deal.interaction_count ?? interactionsQuery.data?.total ?? 0}
          hint={`${deal.competitor_names?.length ?? 0} competitors tracked`}
        />
        <Stat
          label="Open objections"
          value={
            deal.objections?.filter((o) => o.status === "OPEN").length ??
            deal.objection_labels?.length ??
            0
          }
          hint={deal.objection_labels?.join(", ") || "None recorded"}
        />
        <Stat
          label="Owner"
          value={<span className="text-base">{deal.owner_name || "Unassigned"}</span>}
          hint={session?.user.full_name}
        />
      </div>

      <Tabs tabs={TABS} active={tab} onChange={setTab} />

      {tab === "overview" ? (
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="card p-4 lg:col-span-2">
            <SectionTitle title="Deal summary" />
            <p className="text-sm leading-relaxed text-ink-muted">
              {deal.description || "No description recorded."}
            </p>
            <div className="mt-4 grid gap-4 sm:grid-cols-2">
              <div>
                <p className="label">Next action</p>
                <p className="mt-1 text-sm text-ink">{deal.next_action || "—"}</p>
              </div>
              <div>
                <p className="label">Expected close</p>
                <p className="mt-1 text-sm text-ink">{formatDate(deal.expected_close_date)}</p>
              </div>
              {deal.win_reason ? (
                <div>
                  <p className="label">Win reason</p>
                  <p className="mt-1 text-sm text-success">{deal.win_reason}</p>
                </div>
              ) : null}
              {deal.loss_reason ? (
                <div>
                  <p className="label">Loss reason</p>
                  <p className="mt-1 text-sm text-danger">{deal.loss_reason}</p>
                </div>
              ) : null}
            </div>
          </div>

          <div className="space-y-4">
            <div className="card p-4">
              <SectionTitle title="Competitors" />
              <div className="flex flex-wrap gap-1.5">
                {deal.competitors?.length ? (
                  deal.competitors.map((c) => (
                    <span key={c.id} className="chip">
                      {c.name}
                      {c.strength ? ` · ${c.strength}` : ""}
                    </span>
                  ))
                ) : (
                  <p className="text-xs text-ink-faint">No competitors recorded.</p>
                )}
              </div>
            </div>

            <div className="card p-4">
              <SectionTitle title="Objections" />
              <ul className="space-y-2">
                {deal.objections?.length ? (
                  deal.objections.map((o) => (
                    <li key={o.id} className="flex items-start justify-between gap-2 text-xs">
                      <div>
                        <p className="text-ink">{o.label}</p>
                        <p className="text-[11px] text-ink-faint">
                          {o.category || "Uncategorised"} · raised {formatDate(o.raised_at)}
                        </p>
                      </div>
                      <Badge tone={o.status === "OPEN" ? "warning" : "success"}>{o.status}</Badge>
                    </li>
                  ))
                ) : (
                  <p className="text-xs text-ink-faint">No objections logged.</p>
                )}
              </ul>
            </div>
          </div>
        </div>
      ) : null}

      {tab === "timeline" ? (
        timelineQuery.isLoading ? (
          <Loading />
        ) : (
          <ol className="relative ml-3 space-y-4 border-l border-line">
            {(timelineQuery.data ?? []).map((item, index) => (
              <li key={index} className="pl-5">
                <span
                  className={`absolute -left-1.5 mt-1.5 h-3 w-3 rounded-full border-2 ${
                    item.source === "memory"
                      ? "border-accent bg-accent"
                      : item.source === "system"
                        ? "border-warning bg-warning"
                        : "border-line bg-surface-raised"
                  }`}
                />
                <div className="card p-3">
                  <div className="flex items-start justify-between gap-3">
                    <p className="text-sm font-medium text-ink">{item.title}</p>
                    <span className="shrink-0 text-[11px] text-ink-faint">
                      {formatDateTime(item.occurred_at)}
                    </span>
                  </div>
                  {item.detail ? (
                    <p className="mt-1 text-xs leading-relaxed text-ink-muted">{item.detail}</p>
                  ) : null}
                  <div className="mt-2 flex gap-1.5">
                    <Badge tone={item.source === "memory" ? "accent" : "neutral"}>
                      {item.source === "memory" ? "MEMORY INSIGHT" : "DATABASE EVENT"}
                    </Badge>
                    <span className="chip">{item.kind}</span>
                  </div>
                </div>
              </li>
            ))}
          </ol>
        )
      ) : null}

      {tab === "interactions" ? (
        <div className="space-y-3">
          <div className="flex justify-end">
            <Button variant="secondary" onClick={() => setInteractionOpen(true)}>
              <MessageSquare className="h-4 w-4" /> Log interaction
            </Button>
          </div>
          {interactionsQuery.isLoading ? (
            <Loading />
          ) : (interactionsQuery.data?.items ?? []).length === 0 ? (
            <EmptyState
              title="No interactions recorded"
              description="Log a call, meeting or email. The text is analysed for entities and retained in memory."
              action={<Button onClick={() => setInteractionOpen(true)}>Log interaction</Button>}
            />
          ) : (
            <div className="space-y-3">
              {(interactionsQuery.data?.items ?? []).map((item) => (
                <div key={item.id} className="card p-4">
                  <div className="flex items-start justify-between gap-3">
                    <div>
                      <p className="text-sm font-medium text-ink">
                        {item.title || item.interaction_type}
                      </p>
                      <p className="text-[11px] text-ink-faint">
                        {item.interaction_type} · {formatDateTime(item.occurred_at)} ·{" "}
                        {item.channel || "no channel"}
                      </p>
                    </div>
                    {item.sentiment ? (
                      <Badge
                        tone={
                          item.sentiment === "POSITIVE"
                            ? "success"
                            : item.sentiment === "NEGATIVE"
                              ? "danger"
                              : "neutral"
                        }
                      >
                        {item.sentiment}
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-ink-muted">{item.body}</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {item.price_discussed ? (
                      <span className="chip">
                        Price discussed: {money(item.price_discussed, item.currency || "USD")}
                      </span>
                    ) : null}
                    {item.participants?.map((p) => (
                      <span key={p.id} className="chip">
                        {p.name}
                      </span>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {tab === "recommendations" ? (
        <div className="space-y-4">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <p className="text-xs text-ink-faint">
              Every recommendation cites real deals, objections and memories. When evidence is thin
              the system says so instead of guessing.
            </p>
            <Button onClick={() => analyze.mutate()} disabled={analyze.isPending} variant="subtle">
              <Zap className="h-4 w-4" />
              {analyze.isPending ? "Analyzing…" : analysis ? "Re-run analysis" : "Run analysis"}
            </Button>
          </div>

          {analyze.isPending ? (
            <Loading label="Gathering evidence from PostgreSQL and Hindsight…" />
          ) : null}

          {analysis ? (
            <div className="card p-4">
              <SectionTitle
                title="Analysis run"
                subtitle={`Method: ${analysis.method} · memory ${
                  analysis.memory_status.available ? "available" : "unavailable"
                } · LLM ${analysis.llm_status.available ? "available" : "unavailable"}`}
                actions={
                  <Badge tone={analysis.method === "LLM" ? "accent" : "warning"}>
                    {analysis.method}
                  </Badge>
                }
              />
              {analysis.warnings.length ? (
                <ul className="space-y-1 text-xs text-warning">
                  {analysis.warnings.map((w, i) => (
                    <li key={i}>• {w}</li>
                  ))}
                </ul>
              ) : null}
              <div className="mt-3 grid gap-3 sm:grid-cols-2">
                <div>
                  <p className="label">Similar deals used</p>
                  <p className="mt-1 text-lg font-semibold">{analysis.similar_deals.length}</p>
                </div>
                <div>
                  <p className="label">Memory hits</p>
                  <p className="mt-1 text-lg font-semibold">{analysis.memory_hits.length}</p>
                </div>
              </div>
            </div>
          ) : null}

          {recommendationsQuery.isLoading ? (
            <Loading />
          ) : (recommendationsQuery.data?.items ?? []).length === 0 && !analysis ? (
            <EmptyState
              title="No recommendations yet"
              description="Run the analysis to produce evidence-backed next actions for this deal."
              action={<Button onClick={() => analyze.mutate()}>Run analysis</Button>}
            />
          ) : (
            <div className="space-y-4">
              {(recommendationsQuery.data?.items ?? []).map((rec) => (
                <div key={rec.id} className="card p-4">
                  <div className="flex flex-wrap items-start justify-between gap-3">
                    <div className="min-w-0">
                      <div className="flex flex-wrap items-center gap-2">
                        <Badge tone={evidenceTone(rec.evidence_level).includes("success") ? "success" : rec.evidence_level === "INSUFFICIENT_DATA" ? "warning" : "accent"}>
                          {rec.evidence_level.replace(/_/g, " ")}
                        </Badge>
                        <Badge tone="neutral">{rec.kind.replace(/_/g, " ")}</Badge>
                        <Badge tone={rec.source === "LLM" ? "accent" : "neutral"}>
                          {rec.source}
                        </Badge>
                        {rec.risk_level ? <Badge tone="danger">Risk {rec.risk_level}</Badge> : null}
                      </div>
                      <h3 className="mt-2 text-sm font-semibold text-ink">{rec.title}</h3>
                      <p className="mt-1 text-xs leading-relaxed text-ink-muted">{rec.rationale}</p>
                    </div>
                    <div className="flex shrink-0 gap-1">
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

                  {Array.isArray(rec.actions) && rec.actions.length ? (
                    <ul className="mt-3 space-y-2">
                      {(rec.actions as { title?: string; rationale?: string }[]).map(
                        (action, index) => (
                          <li
                            key={index}
                            className="flex gap-2 rounded-lg border border-line bg-surface-sunken p-2.5"
                          >
                            <CheckCircle2 className="mt-0.5 h-3.5 w-3.5 shrink-0 text-accent" />
                            <div>
                              <p className="text-xs font-medium text-ink">
                                {action.title ?? `Action ${index + 1}`}
                              </p>
                              {action.rationale ? (
                                <p className="mt-0.5 text-[11px] text-ink-muted">
                                  {action.rationale}
                                </p>
                              ) : null}
                            </div>
                          </li>
                        ),
                      )}
                    </ul>
                  ) : null}

                  {rec.evidence?.length ? (
                    <div className="mt-3">
                      <p className="label">Evidence</p>
                      <ul className="mt-1.5 space-y-1.5">
                        {rec.evidence.map((item, index) => (
                          <li key={index} className="text-[11px] text-ink-muted">
                            <span className="font-medium text-ink">
                              {String((item as { deal_name?: string }).deal_name ?? "Deal")}
                            </span>{" "}
                            — {String((item as { why?: string }).why ?? item.text ?? "")}
                          </li>
                        ))}
                      </ul>
                    </div>
                  ) : null}

                  {rec.unknowns?.length ? (
                    <div className="mt-3 rounded-lg border border-warning/30 bg-warning/10 p-2.5">
                      <p className="flex items-center gap-1.5 text-[11px] font-medium text-warning">
                        <AlertTriangle className="h-3.5 w-3.5" /> Unknowns
                      </p>
                      <ul className="mt-1 space-y-0.5 text-[11px] text-warning/90">
                        {rec.unknowns.map((u, i) => (
                          <li key={i}>• {u}</li>
                        ))}
                      </ul>
                    </div>
                  ) : null}
                </div>
              ))}
            </div>
          )}
        </div>
      ) : null}

      {tab === "copilot" ? (
        <div className="card flex h-[540px] flex-col p-4">
          <SectionTitle
            title="Deal copilot"
            subtitle="Answers are grounded in this deal's records and memory hits. Citations are shown."
          />
          <div className="flex-1 space-y-3 overflow-y-auto pr-1">
            {copilotLog.length === 0 ? (
              <div className="rounded-lg border border-dashed border-line p-5 text-xs text-ink-faint">
                Ask things like “What objections are still open?”, “Why did similar deals slip?” or
                “What should I do before the next call?”
              </div>
            ) : (
              copilotLog.map((entry, index) => (
                <div
                  key={index}
                  className={`max-w-[85%] rounded-xl px-3.5 py-2.5 text-xs leading-relaxed ${
                    entry.role === "user"
                      ? "ml-auto bg-accent text-white"
                      : "bg-surface-sunken text-ink"
                  }`}
                >
                  <p className="whitespace-pre-wrap">{entry.content}</p>
                  {entry.unavailable ? (
                    <p className="mt-1.5 text-[11px] text-warning">{entry.unavailable}</p>
                  ) : null}
                  {entry.citations?.length ? (
                    <ul className="mt-2 space-y-1 border-t border-line pt-2 text-[11px] text-ink-muted">
                      {entry.citations.map((c, i) => (
                        <li key={i}>↳ {c.title || c.text || c.source || "source"}</li>
                      ))}
                    </ul>
                  ) : null}
                </div>
              ))
            )}
          </div>
          <form
            className="mt-3 flex gap-2"
            onSubmit={(event) => {
              event.preventDefault();
              const question = copilotInput.trim();
              if (!question) return;
              setCopilotInput("");
              askCopilot.mutate(question);
            }}
          >
            <Input
              value={copilotInput}
              onChange={(e) => setCopilotInput(e.target.value)}
              placeholder="Ask about this deal…"
              disabled={askCopilot.isPending}
            />
            <Button type="submit" disabled={askCopilot.isPending || !copilotInput.trim()}>
              <Send className="h-4 w-4" />
            </Button>
          </form>
        </div>
      ) : null}

      {tab === "memory" ? (
        memoryQuery.isLoading ? (
          <Loading label="Querying Hindsight…" />
        ) : memoryQuery.data ? (
          <div className="grid gap-4 lg:grid-cols-3">
            <div className="card p-4 lg:col-span-2">
              <SectionTitle
                title="Recalled from Hindsight"
                subtitle={`Bank ${memoryQuery.data.status.bank_id ?? "n/a"} · ${
                  memoryQuery.data.status.available
                    ? `v${memoryQuery.data.status.version ?? "?"}`
                    : memoryQuery.data.status.reason
                }`}
                actions={
                  <Badge tone={memoryQuery.data.status.available ? "success" : "warning"}>
                    {memoryQuery.data.status.available ? "AVAILABLE" : "UNAVAILABLE"}
                  </Badge>
                }
              />
              {memoryQuery.data.recalled.length === 0 ? (
                <EmptyState
                  title="No memory recalled for this deal"
                  description="Memory is retained when interactions are logged. If Hindsight is down, records stay in PostgreSQL and are re-synced later."
                />
              ) : (
                <ul className="space-y-2">
                  {memoryQuery.data.recalled.map((hit) => (
                    <li key={hit.id} className="rounded-lg border border-line bg-surface-sunken p-3">
                      <p className="text-xs leading-relaxed text-ink">{hit.text}</p>
                      <div className="mt-1.5 flex flex-wrap gap-1.5">
                        {hit.tags?.map((t) => (
                          <span key={t} className="chip">
                            {t}
                          </span>
                        ))}
                        {hit.score ? (
                          <span className="chip">score {hit.score.toFixed(2)}</span>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}

              {memoryQuery.data.related_count ? (
                <div className="mt-4">
                  <p className="label">
                    Related memories from other deals ({memoryQuery.data.related_count})
                  </p>
                  <ul className="mt-2 space-y-2">
                    {(memoryQuery.data.related ?? []).map((hit) => (
                      <li key={hit.id} className="rounded-lg border border-dashed border-line p-2.5">
                        <p className="text-[11px] leading-relaxed text-ink-muted">{hit.text}</p>
                      </li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </div>

            <div className="card p-4">
              <SectionTitle
                title="Local memory index"
                subtitle={`${memoryQuery.data.total} references`}
              />
              <ul className="space-y-2 overflow-y-auto" style={{ maxHeight: 360 }}>
                {memoryQuery.data.references.map((ref) => (
                  <li key={String(ref.id)} className="rounded-lg border border-line p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <span className="chip">{String(ref.kind)}</span>
                      <span
                        className={`text-[10px] ${
                          ref.sync_status === "SYNCED" ? "text-success" : "text-danger"
                        }`}
                      >
                        {String(ref.sync_status)}
                      </span>
                    </div>
                    <p className="mt-1.5 line-clamp-3 text-[11px] text-ink-muted">
                      {String(ref.content).slice(0, 240)}
                    </p>
                    <p className="mt-1 text-[10px] text-ink-faint">{relativeTime(String(ref.created_at))}</p>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        ) : null
      ) : null}

      <InteractionModal
        open={interactionOpen}
        onClose={() => setInteractionOpen(false)}
        pending={addInteraction.isPending}
        onSubmit={(payload) => addInteraction.mutate(payload)}
      />

      <OutcomeModal
        open={outcomeOpen}
        onClose={() => setOutcomeOpen(false)}
        pending={recordOutcome.isPending}
        onSubmit={(payload) => recordOutcome.mutate(payload)}
      />
    </div>
  );
}

function InteractionModal({
  open,
  onClose,
  pending,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  pending: boolean;
  onSubmit: (payload: Record<string, unknown>) => void;
}) {
  const [form, setForm] = useState({
    interaction_type: "CALL",
    title: "",
    body: "",
    channel: "video",
    price_discussed: "",
    sentiment: "NEUTRAL",
  });

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  return (
    <Modal open={open} onClose={onClose} title="Log an interaction">
      <div className="space-y-3">
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Type">
            <Select value={form.interaction_type} onChange={set("interaction_type")}>
              {["CALL", "MEETING", "EMAIL", "NOTE", "PROPOSAL", "PRICING_DISCUSSION", "OBJECTION", "COMPETITOR_DISCUSSION", "TRANSCRIPT"].map(
                (t) => (
                  <option key={t} value={t}>
                    {t.replace(/_/g, " ")}
                  </option>
                ),
              )}
            </Select>
          </Field>
          <Field label="Channel">
            <Select value={form.channel} onChange={set("channel")}>
              {["video", "phone", "email", "in-person", "chat"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
        </div>
        <Field label="Title">
          <Input value={form.title} onChange={set("title")} placeholder="Discovery call" />
        </Field>
        <Field
          label="What happened"
          hint="Entities, commitments and requirements are extracted from this text and retained in memory."
        >
          <textarea
            className="input min-h-[130px] resize-y"
            value={form.body}
            onChange={set("body")}
            placeholder="Describe the conversation, objections raised, pricing discussed…"
            required
          />
        </Field>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Price discussed">
            <Input
              type="number"
              min="0"
              step="0.01"
              value={form.price_discussed}
              onChange={set("price_discussed")}
              placeholder="Optional"
            />
          </Field>
          <Field label="Sentiment">
            <Select value={form.sentiment} onChange={set("sentiment")}>
              {["POSITIVE", "NEUTRAL", "NEGATIVE"].map((t) => (
                <option key={t} value={t}>
                  {t}
                </option>
              ))}
            </Select>
          </Field>
          <div className="flex items-end">
            <Button
              className="w-full"
              disabled={pending || !form.body.trim()}
              onClick={() =>
                onSubmit({
                  interaction_type: form.interaction_type,
                  title: form.title,
                  body: form.body,
                  channel: form.channel,
                  sentiment: form.sentiment,
                  price_discussed: form.price_discussed ? Number(form.price_discussed) : null,
                  currency: form.price_discussed ? "USD" : null,
                })
              }
            >
              {pending ? "Saving…" : "Save"}
            </Button>
          </div>
        </div>
      </div>
    </Modal>
  );
}

function OutcomeModal({
  open,
  onClose,
  pending,
  onSubmit,
}: {
  open: boolean;
  onClose: () => void;
  pending: boolean;
  onSubmit: (payload: Record<string, unknown>) => void;
}) {
  const [outcome, setOutcome] = useState("WON");
  const [reason, setReason] = useState("");

  return (
    <Modal open={open} onClose={onClose} title="Record an outcome">
      <div className="space-y-3">
        <Field label="Outcome">
          <Select value={outcome} onChange={(e) => setOutcome(e.target.value)}>
            <option value="WON">Won</option>
            <option value="LOST">Lost</option>
          </Select>
        </Field>
        <Field label={outcome === "WON" ? "Win reason" : "Loss reason"}>
          <textarea
            className="input min-h-[110px] resize-y"
            value={reason}
            onChange={(e) => setReason(e.target.value)}
            placeholder="Why did this happen?"
          />
        </Field>
        <Button
          className="w-full"
          disabled={pending}
          onClick={() =>
            onSubmit({
              outcome,
              [outcome === "WON" ? "win_reason" : "loss_reason"]: reason,
            })
          }
        >
          {pending ? "Saving…" : "Record outcome"}
        </Button>
      </div>
    </Modal>
  );
}
