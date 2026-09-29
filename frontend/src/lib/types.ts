export type Role = "ADMIN" | "SALES_MANAGER" | "SALES_REP";

export interface Session {
  access_token: string;
  token_type: string;
  expires_at: string;
  user: CurrentUser;
  organization: {
    id: string;
    name: string;
    slug: string;
    industry?: string | null;
    is_demo: boolean;
  };
  permissions: string[];
}

export interface CurrentUser {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  title?: string | null;
  organization_id: string;
  is_active: boolean;
  created_at: string;
}

export interface Paged<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface Contact {
  id: string;
  full_name: string;
  title?: string | null;
  email?: string | null;
  phone?: string | null;
  is_decision_maker?: boolean;
  is_procurement?: boolean;
  influence?: string | null;
  notes?: string | null;
}

export interface Customer {
  id: string;
  name: string;
  domain?: string | null;
  industry?: string | null;
  segment?: string | null;
  region?: string | null;
  employee_count?: number | null;
  notes?: string | null;
  contacts?: Contact[];
}

export interface Deal {
  id: string;
  name: string;
  customer_id: string;
  customer_name?: string;
  owner_id: string;
  owner_name?: string;
  amount: string | number;
  currency: string;
  stage: string;
  probability: number;
  status: string;
  outcome?: string | null;
  expected_close_date?: string | null;
  last_activity_at?: string | null;
  next_action?: string | null;
  description?: string | null;
  win_reason?: string | null;
  loss_reason?: string | null;
  created_at: string;
  updated_at?: string;
  is_demo?: boolean;
  competitor_names?: string[];
  objection_labels?: string[];
  interaction_count?: number;
  risk_level?: string | null;
}

export interface Interaction {
  id: string;
  deal_id: string;
  interaction_type: string;
  title: string;
  body: string;
  channel?: string | null;
  sentiment?: string | null;
  price_discussed?: number | string | null;
  currency?: string | null;
  occurred_at: string;
  participants?: { id: string; name: string; role?: string | null; side?: string | null }[];
}

export interface EvidenceItem {
  type?: string;
  source?: string;
  deal_id?: string | null;
  deal_name?: string;
  customer_name?: string | null;
  outcome?: string | null;
  stage?: string | null;
  amount?: string | number | null;
  why?: string;
  reference_id?: string;
  text?: string;
  occurred_at?: string | null;
  score?: number | null;
}

export interface RecommendationAction {
  title?: string;
  action?: string;
  rationale?: string;
  evidence_ids?: string[];
}

export interface Recommendation {
  id: string;
  deal_id: string;
  deal_name?: string;
  kind: string;
  title: string;
  rationale: string;
  summary?: string | null;
  actions?: RecommendationAction[] | Record<string, unknown>[];
  evidence?: EvidenceItem[];
  unknowns?: string[];
  risks?: { title?: string; detail?: string; level?: string }[];
  similar_patterns?: string[];
  evidence_level: string;
  risk_level?: string | null;
  source: string;
  status: string;
  model?: string | null;
  created_at: string;
  feedback?: { id: string; feedback: string; comment?: string | null }[];
}

export interface MemoryReference {
  id: string;
  deal_id?: string | null;
  customer_id?: string | null;
  bank_id: string;
  kind: string;
  content: string;
  context?: string | null;
  meta?: Record<string, unknown> | null;
  tags?: string[] | null;
  occurred_at?: string | null;
  sync_status: string;
  sync_error?: string | null;
  created_at: string;
}

export interface TimelineItem {
  source: "database" | "memory" | "system";
  occurred_at: string;
  title: string;
  detail?: string | null;
  kind: string;
  reference_id?: string | null;
  meta?: Record<string, unknown>;
}

export interface MemoryStatus {
  available: boolean;
  configured_url: string;
  enabled: boolean;
  bank_id?: string | null;
  version?: string | null;
  reason?: string | null;
  code?: string | null;
  local_reference_count: number;
}

export interface ChartPoint {
  label: string;
  value: number;
  secondary?: number | null;
}

export interface KPIS {
  active_deals: number;
  pipeline_value: number | string;
  won_deals: number;
  lost_deals: number;
  win_rate?: number | null;
  average_deal_size?: number | string | null;
  average_sales_cycle_days?: number | null;
  closed_total: number;
}

export interface Dashboard {
  kpis: KPIS;
  pipeline_by_stage: ChartPoint[];
  win_loss: ChartPoint[];
  loss_reasons: ChartPoint[];
  competitor_outcomes: Record<string, unknown>[];
  objections: ChartPoint[];
  deal_trend: ChartPoint[];
  recent_activity: { title?: string; detail?: string; occurred_at?: string; kind?: string }[];
  top_competitors: ChartPoint[];
  top_objections: ChartPoint[];
}

export interface WinLoss {
  kpis: KPIS;
  win_loss_distribution: ChartPoint[];
  pipeline_by_stage: ChartPoint[];
  common_objections: ChartPoint[];
  common_competitors: ChartPoint[];
  loss_reasons: ChartPoint[];
  win_reasons: ChartPoint[];
  stage_failure_rates: ChartPoint[];
  competitor_outcomes: Record<string, unknown>[];
  pricing_related_losses: number;
  competitor_related_losses: number;
  recurring_requirements: ChartPoint[];
  sufficient_data: boolean;
  data_quality: Record<string, unknown>;
  insufficient_reason?: string | null;
}

export interface SearchHit {
  entity_type: string;
  id: string;
  title: string;
  subtitle?: string | null;
  score: number;
  extra: Record<string, unknown>;
}
