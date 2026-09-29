import {
  Activity,
  BarChart3,
  Brain,
  Lightbulb,
  LogOut,
  Moon,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Sun,
  Users,
  LayoutDashboard,
  GitBranch,
} from "lucide-react";
import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, useLocation, useNavigate } from "react-router-dom";
import { useAuth } from "../lib/auth";
import { cn } from "../lib/utils";

const NAV = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/pipeline", label: "Pipeline", icon: GitBranch },
  { to: "/customers", label: "Customers", icon: Users },
  { to: "/recommendations", label: "Recommendations", icon: Lightbulb },
  { to: "/analytics", label: "Win / Loss", icon: BarChart3 },
  { to: "/memory", label: "Memory Explorer", icon: Brain },
  { to: "/settings", label: "System Health", icon: Settings },
];

export default function Layout({ children }: { children: ReactNode }) {
  const { session, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [collapsed, setCollapsed] = useState(false);
  const [query, setQuery] = useState("");
  const [dark, setDark] = useState(() => document.documentElement.classList.contains("dark"));

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  const submitSearch = (event: React.FormEvent) => {
    event.preventDefault();
    if (!query.trim()) return;
    navigate(`/search?q=${encodeURIComponent(query.trim())}`);
  };

  return (
    <div className="flex min-h-screen bg-surface">
      <aside
        className={cn(
          "sticky top-0 flex h-screen flex-col border-r border-line bg-surface-raised transition-all",
          collapsed ? "w-16" : "w-60",
        )}
      >
        <div className="flex h-14 items-center justify-between border-b border-line px-4">
          {!collapsed && (
            <Link to="/" className="flex items-center gap-2">
              <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent text-[13px] font-bold text-white">
                DI
              </span>
              <span className="text-sm font-semibold tracking-tight">Deal Intelligence</span>
            </Link>
          )}
          <button
            onClick={() => setCollapsed((v) => !v)}
            className="rounded-md p-1.5 text-ink-faint hover:bg-surface-sunken hover:text-ink"
            aria-label="Toggle sidebar"
          >
            {collapsed ? <PanelLeftOpen className="h-4 w-4" /> : <PanelLeftClose className="h-4 w-4" />}
          </button>
        </div>

        <nav className="flex-1 space-y-0.5 p-2">
          {NAV.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 rounded-lg px-3 py-2 text-sm transition",
                  isActive
                    ? "bg-accent-soft text-accent"
                    : "text-ink-muted hover:bg-surface-sunken hover:text-ink",
                  collapsed && "justify-center px-0",
                )
              }
              title={item.label}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </NavLink>
          ))}
        </nav>

        <div className="border-t border-line p-2">
          <button
            onClick={() => setDark((v) => !v)}
            className={cn(
              "flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-muted transition hover:bg-surface-sunken hover:text-ink",
              collapsed && "justify-center px-0",
            )}
            title="Toggle theme"
          >
            {dark ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
            {!collapsed && <span>{dark ? "Light mode" : "Dark mode"}</span>}
          </button>
          {!collapsed && session ? (
            <div className="mt-2 rounded-lg border border-line bg-surface-sunken px-3 py-2">
              <p className="truncate text-xs font-medium text-ink">{session.user.full_name}</p>
              <p className="truncate text-[11px] text-ink-faint">{session.user.email}</p>
              <p className="mt-0.5 text-[10px] uppercase tracking-wide text-ink-faint">
                {session.user.role.replace("_", " ")}
              </p>
            </div>
          ) : null}
          <button
            onClick={async () => {
              await logout();
              navigate("/login");
            }}
            className={cn(
              "mt-1 flex w-full items-center gap-3 rounded-lg px-3 py-2 text-sm text-ink-muted transition hover:bg-surface-sunken hover:text-danger",
              collapsed && "justify-center px-0",
            )}
            title="Sign out"
          >
            <LogOut className="h-4 w-4" />
            {!collapsed && <span>Sign out</span>}
          </button>
        </div>
      </aside>

      <div className="flex min-w-0 flex-1 flex-col">
        <header className="sticky top-0 z-30 flex h-14 items-center gap-4 border-b border-line bg-surface-raised/90 px-6 backdrop-blur">
          <form onSubmit={submitSearch} className="relative w-full max-w-md">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-ink-faint" />
            <input
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder="Search deals, customers, interactions…"
              className="input h-9 pl-9 text-sm"
            />
          </form>
          <div className="ml-auto flex items-center gap-3 text-xs text-ink-faint">
            <Activity className="h-3.5 w-3.5 text-success" />
            <span className="hidden sm:inline">PostgreSQL + Hindsight memory</span>
          </div>
        </header>

        <main className="min-w-0 flex-1 px-6 py-6" key={location.pathname}>
          {children}
        </main>
      </div>
    </div>
  );
}
