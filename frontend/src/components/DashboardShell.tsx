"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { useMode } from "./ModeProvider";
import { VestigoLogo } from "./VestigoLogo";

type NavKey =
  | "Dashboard"
  | "Screener"
  | "Strategies"
  | "Quant"
  | "AI"
  | "Backtest";

type NavItem = {
  label: NavKey;
  href: string;
  /** Visible in Lite mode. Pro-only items disappear (not locked) in Lite. */
  lite: boolean;
  /** SVG path for the nav icon (24x24 viewBox). */
  icon: string;
};

const NAV_ITEMS: NavItem[] = [
  { label: "Dashboard", href: "/", lite: true, icon: "M3 12l9-8 9 8M5 10v9h14v-9" },
  { label: "Screener", href: "/screener", lite: true, icon: "M4 6h16M4 12h10M4 18h6" },
  { label: "Strategies", href: "/strategies", lite: false, icon: "M4 18V8m5 10V4m5 14v-7m5 7V9" },
  { label: "Quant", href: "/quant", lite: false, icon: "M4 19l5-6 4 3 6-9M4 19h16" },
  { label: "AI", href: "/ai", lite: true, icon: "M12 3l2 5 5 2-5 2-2 5-2-5-5-2 5-2z" },
  { label: "Backtest", href: "/backtest", lite: false, icon: "M4 5h16v14H4zM4 10h16M9 5v14" },
];

const PRO_ONLY_PATHS = NAV_ITEMS.filter((i) => !i.lite).map((i) => i.href);

const DISCLAIMER_TEXT =
  "Alat bantu analisis & edukasi, BUKAN nasihat keuangan. Keputusan investasi tanggung jawab Anda.";

function NavIcon({ d }: { d: string }) {
  return (
    <svg
      viewBox="0 0 24 24"
      width="17"
      height="17"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.6"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d={d} />
    </svg>
  );
}

function ModeToggle({
  mode,
  onChange,
}: {
  mode: "LITE" | "PRO";
  onChange: (m: "LITE" | "PRO") => void;
}) {
  return (
    <div className="seg" role="tablist" aria-label="Mode tampilan">
      {(["LITE", "PRO"] as const).map((m) => (
        <button
          key={m}
          role="tab"
          aria-selected={mode === m}
          className={`seg-btn ${mode === m ? "seg-on" : ""}`}
          onClick={() => onChange(m)}
        >
          {m === "LITE" ? "Lite" : "Pro"}
        </button>
      ))}
    </div>
  );
}

type DashboardShellProps = {
  children: ReactNode;
  activeNav?: NavKey | string;
  eyebrow?: string;
  title?: string;
};

export function DashboardShell({
  children,
  activeNav = "Dashboard",
  eyebrow = "IDX Stock Screener",
  title = "Dashboard",
}: DashboardShellProps) {
  const { mode, setMode, ready, dataDate } = useMode();
  const pathname = usePathname();
  const router = useRouter();

  const [bannerOpen, setBannerOpen] = useState(true);
  const [showOnboard, setShowOnboard] = useState(false);
  const onboardTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Banner dismissal persists (one global disclaimer, 6.11).
  useEffect(() => {
    if (window.localStorage.getItem("vestigo.banner") === "0") setBannerOpen(false);
  }, []);

  // Lite reflow: a Pro-only route is unreachable in Lite - bounce to Dashboard.
  useEffect(() => {
    if (ready && mode === "LITE" && PRO_ONLY_PATHS.includes(pathname)) {
      router.replace("/");
    }
  }, [ready, mode, pathname, router]);

  const handleModeChange = (next: "LITE" | "PRO") => {
    if (next === "PRO" && mode !== "PRO") {
      // First time on Pro: show the onboarding tooltip once.
      if (window.localStorage.getItem("vestigo.proSeen") !== "1") {
        window.localStorage.setItem("vestigo.proSeen", "1");
        setShowOnboard(true);
        if (onboardTimer.current) clearTimeout(onboardTimer.current);
        onboardTimer.current = setTimeout(() => setShowOnboard(false), 4200);
      }
    }
    setMode(next);
  };

  useEffect(() => {
    return () => {
      if (onboardTimer.current) clearTimeout(onboardTimer.current);
    };
  }, []);

  const dismissBanner = () => {
    setBannerOpen(false);
    try {
      window.localStorage.setItem("vestigo.banner", "0");
    } catch {
      /* ignore */
    }
  };

  const navItems = NAV_ITEMS.filter((item) => mode === "PRO" || item.lite);

  return (
    <div className="app">
      <aside className="sidebar">
        <div className="brand">
          <p className="eyebrow brand-eyebrow">IDX Stock Screener</p>
          <div className="wordmark-row">
            <VestigoLogo size={30} className="trail" />
            <span className="wordmark">Vestigo</span>
          </div>
        </div>

        <nav className="nav">
          {navItems.map((item) => (
            <Link
              key={item.label}
              href={item.href}
              className={`nav-item ${item.label === activeNav ? "nav-on" : ""}`}
            >
              <NavIcon d={item.icon} />
              <span>{item.label}</span>
            </Link>
          ))}
        </nav>

        <div className="side-foot">
          <div className="avatar">
            <VestigoLogo size={20} />
          </div>
          <div className="side-foot-txt">
            <p>© 2026</p>
            <p>Anak Agung Aryadipa Aditya Nugraha</p>
            <p>All rights reserved</p>
          </div>
        </div>
      </aside>

      <main className="main">
        {bannerOpen && (
          <div className="global-banner">
            <span>{DISCLAIMER_TEXT}</span>
            <button className="banner-x" onClick={dismissBanner} aria-label="Tutup">
              ×
            </button>
          </div>
        )}

        <header className="topbar">
          <div>
            <p className="eyebrow">{eyebrow}</p>
            <h1 className="page-title">{title}</h1>
          </div>
          <div className="topbar-ctrls">
            <ModeToggle mode={mode} onChange={handleModeChange} />
          </div>
        </header>

        {showOnboard && (
          <div className="onboard">
            Mode Pro membuka Backtest, Quant, dan matriks strategi.
          </div>
        )}

        <div className="content content-fade">{children}</div>

        <footer className="app-foot">
          <span>Vestigo · IDX stock screener</span>
          <span className="t3">
            {dataDate ? `Data per ${dataDate} · ` : ""}alat edukasi, bukan nasihat keuangan
          </span>
        </footer>
      </main>
    </div>
  );
}
