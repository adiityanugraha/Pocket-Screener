import Link from "next/link";
import type { ReactNode } from "react";

const navItems = [
  { label: "Dashboard", href: "/" },
  { label: "Backtest", href: "/backtest" },
];

const marketStats = [
  { label: "BSJP", value: "Top 5", tone: "text-emerald-300" },
  { label: "BPJS", value: "Top 5", tone: "text-sky-300" },
  { label: "Timeframe", value: "Daily", tone: "text-amber-300" },
];

type DashboardShellProps = {
  children: ReactNode;
  activeNav?: string;
  eyebrow?: string;
  title?: string;
};

export function DashboardShell({
  children,
  activeNav = "Dashboard",
  eyebrow = "IDX Daily Screener",
  title = "Dashboard",
}: DashboardShellProps) {
  return (
    <main className="min-h-screen bg-[#060a14] text-slate-100">
      <div className="flex min-h-screen">
        <aside className="sticky top-0 hidden h-screen w-64 shrink-0 border-r border-white/10 bg-[#090e1c] px-5 py-6 lg:block">
          <div className="flex h-full flex-col">
            <div>
              <p className="text-xs font-semibold uppercase tracking-[0.28em] text-sky-300">
                Pocket
              </p>
              <h1 className="mt-2 text-xl font-semibold text-white">
                Screener
              </h1>
            </div>

            <nav className="mt-8 flex flex-col gap-1">
              {navItems.map((item) => (
                <Link
                  className={`rounded-lg px-3 py-2 text-sm transition-colors ${
                    item.label === activeNav
                      ? "bg-white/10 text-white"
                      : "text-slate-400 hover:bg-white/[0.06] hover:text-slate-100"
                  }`}
                  href={item.href}
                  key={item.label}
                >
                  {item.label}
                </Link>
              ))}
            </nav>

            <div className="mt-auto rounded-lg border border-white/10 bg-white/[0.04] p-4">
              <p className="text-xs text-slate-400">Mode</p>
              <p className="mt-1 text-sm font-medium text-slate-100">
                No-backend phase
              </p>
            </div>
          </div>
        </aside>

        <div className="min-w-0 flex-1">
          <header className="sticky top-0 z-20 border-b border-white/10 bg-[#060a14]/90 backdrop-blur">
            <div className="mx-auto flex max-w-7xl flex-col gap-4 px-4 py-4 sm:px-6 xl:px-8">
              <div className="flex flex-col justify-between gap-4 md:flex-row md:items-center">
                <div>
                  <p className="text-xs font-semibold uppercase tracking-[0.24em] text-slate-400">
                    {eyebrow}
                  </p>
                  <h2 className="mt-2 text-2xl font-semibold tracking-normal text-white md:text-3xl">
                    {title}
                  </h2>
                </div>

                <div className="grid grid-cols-3 gap-2 sm:gap-3">
                  {marketStats.map((stat) => (
                    <div
                      className="rounded-lg border border-white/10 bg-white/[0.04] px-3 py-2.5 transition-colors hover:border-white/20 hover:bg-white/[0.06] sm:px-4 sm:py-3"
                      key={stat.label}
                    >
                      <p className="text-[11px] text-slate-400 sm:text-xs">
                        {stat.label}
                      </p>
                      <p
                        className={`mt-1 text-base font-semibold sm:text-lg ${stat.tone}`}
                      >
                        {stat.value}
                      </p>
                    </div>
                  ))}
                </div>
              </div>

              <nav className="flex gap-2 overflow-x-auto lg:hidden">
                {navItems.map((item) => (
                  <Link
                    className={`shrink-0 rounded-lg px-3 py-2 text-sm ${
                      item.label === activeNav
                        ? "bg-white/10 text-white"
                        : "text-slate-400"
                    }`}
                    href={item.href}
                    key={item.label}
                  >
                    {item.label}
                  </Link>
                ))}
              </nav>
            </div>
          </header>

          <div className="animate-fade-in mx-auto flex max-w-7xl flex-col gap-6 px-4 py-6 sm:px-6 xl:px-8">
            {children}
          </div>
        </div>
      </div>
    </main>
  );
}
