import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Building2, Plus } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router-dom";
import { Badge, Button, EmptyState, ErrorNote, Field, Input, Loading, Modal, Select } from "../components/ui";
import { api, queryString } from "../lib/api";
import type { Customer, Paged } from "../lib/types";

export default function Customers() {
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    name: "",
    domain: "",
    industry: "",
    segment: "Mid-Market",
    region: "AMER",
  });
  const [error, setError] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["customers", search],
    queryFn: () => api.get<Paged<Customer>>(`/customers${queryString({ search, limit: 100 })}`),
  });

  const create = useMutation({
    mutationFn: () => api.post<Customer>("/customers", { ...form, name: form.name.trim() }),
    onSuccess: () => {
      setOpen(false);
      setForm({ name: "", domain: "", industry: "", segment: "Mid-Market", region: "AMER" });
      void qc.invalidateQueries({ queryKey: ["customers"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : "Could not create customer."),
  });

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Customers</h1>
          <p className="text-xs text-ink-faint">{data?.total ?? 0} accounts</p>
        </div>
        <div className="flex items-center gap-2">
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Search customers…"
            className="h-9 w-56"
          />
          <Button onClick={() => setOpen(true)}>
            <Plus className="h-4 w-4" /> New customer
          </Button>
        </div>
      </div>

      {isLoading ? (
        <Loading />
      ) : (data?.items ?? []).length === 0 ? (
        <EmptyState
          title="No customers yet"
          description="Create an account to start tracking deals and interactions."
          action={<Button onClick={() => setOpen(true)}>New customer</Button>}
        />
      ) : (
        <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
          {(data?.items ?? []).map((customer) => (
            <Link key={customer.id} to={`/customers/${customer.id}`} className="card p-4 transition hover:border-accent/50">
              <div className="flex items-start justify-between gap-2">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-accent-soft text-accent">
                  <Building2 className="h-4 w-4" />
                </span>
                {customer.segment ? <Badge>{customer.segment}</Badge> : null}
              </div>
              <p className="mt-3 truncate text-sm font-medium text-ink">{customer.name}</p>
              <p className="truncate text-xs text-ink-faint">
                {customer.industry || "Industry unknown"} · {customer.region || "Region unknown"}
              </p>
              <p className="mt-2 text-[11px] text-ink-faint">{customer.domain}</p>
            </Link>
          ))}
        </div>
      )}

      <Modal open={open} onClose={() => setOpen(false)} title="New customer">
        <div className="space-y-3">
          {error ? <ErrorNote message={error} /> : null}
          <Field label="Name">
            <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required />
          </Field>
          <Field label="Domain">
            <Input
              value={form.domain}
              onChange={(e) => setForm({ ...form, domain: e.target.value })}
              placeholder="acme.com"
            />
          </Field>
          <div className="grid gap-3 sm:grid-cols-3">
            <Field label="Industry">
              <Input value={form.industry} onChange={(e) => setForm({ ...form, industry: e.target.value })} />
            </Field>
            <Field label="Segment">
              <Select value={form.segment} onChange={(e) => setForm({ ...form, segment: e.target.value })}>
                {["SMB", "Mid-Market", "Enterprise"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </Select>
            </Field>
            <Field label="Region">
              <Select value={form.region} onChange={(e) => setForm({ ...form, region: e.target.value })}>
                {["AMER", "EMEA", "APAC"].map((s) => (
                  <option key={s}>{s}</option>
                ))}
              </Select>
            </Field>
          </div>
          <Button
            className="w-full"
            disabled={create.isPending || !form.name.trim()}
            onClick={() => create.mutate()}
          >
            {create.isPending ? "Creating…" : "Create customer"}
          </Button>
        </div>
      </Modal>
    </div>
  );
}
