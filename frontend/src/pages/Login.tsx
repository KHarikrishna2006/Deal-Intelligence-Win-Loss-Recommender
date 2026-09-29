import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { Button, ErrorNote, Field, Input } from "../components/ui";
import { useAuth } from "../lib/auth";
import { ApiError } from "../lib/api";

export default function Login() {
  const { login, register } = useAuth();
  const navigate = useNavigate();
  const [mode, setMode] = useState<"login" | "register">("login");
  const [form, setForm] = useState({
    email: "admin@northwind-analytics.com",
    password: "demo-password-123",
    full_name: "",
    organization_name: "",
    title: "",
  });
  const [error, setError] = useState<string | null>(null);

  const mutation = useMutation({
    mutationFn: async () => {
      setError(null);
      if (mode === "login") {
        await login(form.email, form.password);
      } else {
        await register({
          email: form.email,
          password: form.password,
          full_name: form.full_name,
          organization_name: form.organization_name,
          title: form.title || undefined,
        });
      }
    },
    onSuccess: () => navigate("/", { replace: true }),
    onError: (err) => setError(err instanceof ApiError ? err.message : "Something went wrong."),
  });

  const set = (key: keyof typeof form) => (event: React.ChangeEvent<HTMLInputElement>) =>
    setForm((prev) => ({ ...prev, [key]: event.target.value }));

  return (
    <div className="flex min-h-screen items-center justify-center bg-surface px-4">
      <div className="w-full max-w-md">
        <div className="mb-6 flex items-center gap-3">
          <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-accent text-sm font-bold text-white">
            DI
          </span>
          <div>
            <h1 className="text-lg font-semibold tracking-tight">Deal Intelligence</h1>
            <p className="text-xs text-ink-faint">AI deal intelligence &amp; win/loss recommender</p>
          </div>
        </div>

        <div className="card p-6">
          <div className="mb-5 flex gap-1 rounded-lg bg-surface-sunken p-1">
            {(["login", "register"] as const).map((item) => (
              <button
                key={item}
                onClick={() => setMode(item)}
                className={`flex-1 rounded-md px-3 py-1.5 text-xs font-medium transition ${
                  mode === item ? "bg-surface-raised text-ink shadow-sm" : "text-ink-faint"
                }`}
              >
                {item === "login" ? "Sign in" : "Create workspace"}
              </button>
            ))}
          </div>

          <form
            className="space-y-3"
            onSubmit={(event) => {
              event.preventDefault();
              mutation.mutate();
            }}
          >
            {mode === "register" && (
              <>
                <Field label="Full name">
                  <Input
                    value={form.full_name}
                    onChange={set("full_name")}
                    placeholder="Jordan Reyes"
                    required
                  />
                </Field>
                <Field label="Organisation">
                  <Input
                    value={form.organization_name}
                    onChange={set("organization_name")}
                    placeholder="Northwind Analytics"
                    required
                  />
                </Field>
              </>
            )}
            <Field label="Work email">
              <Input type="email" value={form.email} onChange={set("email")} required />
            </Field>
            <Field label="Password" hint={mode === "register" ? "Minimum 8 characters." : undefined}>
              <Input
                type="password"
                value={form.password}
                onChange={set("password")}
                required
                minLength={8}
              />
            </Field>

            {error ? <ErrorNote message={error} /> : null}

            <Button type="submit" className="w-full" disabled={mutation.isPending}>
              {mutation.isPending
                ? "Working…"
                : mode === "login"
                  ? "Sign in"
                  : "Create workspace"}
            </Button>
          </form>

          <div className="mt-5 rounded-lg border border-dashed border-line bg-surface-sunken p-3 text-[11px] leading-relaxed text-ink-faint">
            <p className="font-medium text-ink-muted">Demo accounts</p>
            <p className="mt-1 font-mono">admin@northwind-analytics.com</p>
            <p className="font-mono">manager@northwind-analytics.com</p>
            <p className="font-mono">rep@northwind-analytics.com</p>
            <p className="mt-1">password: demo-password-123</p>
          </div>
        </div>
      </div>
    </div>
  );
}
