import { ReactNode, useState } from "react";
import {
  LayoutDashboard,
  FileText,
  FolderOpen,
  Package,
  Users,
  Upload,
  Sparkles,
  ChartNoAxesCombined,
  History,
  TriangleAlert,
  Tags,
  Settings,
  MonitorCog,
  Menu,
  X,
  Pin,
  ReceiptText,
  MessageSquareText,
  ShieldCheck,
  LogOut,
  MapPin,
  TrendingUp,
  Trophy,
  MessageSquareWarning,
  Globe2,
  BedDouble,
  HeartPulse,
  House as Home,
} from "lucide-react";
import { clearAuth, currentUser, eyeApi } from "../lib/api";
import { CacheChip } from "./CacheStatus";
import { supabaseOnline } from "../lib/supabaseDataService";
// Versione online (sola lettura): solo le pagine servite da Supabase.
const ONLINE_PAGES: Page[] = ["home", "invoices", "products", "suppliers", "users"];
export type Page =
  | "home"
  | "dashboard"
  | "invoices"
  | "invoice-files"
  | "products"
  | "suppliers"
  | "import"
  | "ai"
  | "reports"
  | "history-report"
  | "destinations"
  | "history"
  | "anomalies"
  | "categories"
  | "settings"
  | "system"
  | "feedback"
  | "health"
  | "users";
const nav: [Page, string, any][] = [
  ["home", "Home", Home],
  ["dashboard", "Dashboard", LayoutDashboard],
  ["invoices", "Fatture", FileText],
  ["invoice-files", "Archivio file", FolderOpen],
  ["products", "Prodotti", Package],
  ["suppliers", "Fornitori", Users],
  ["import", "Importa", Upload],
  ["destinations", "Destinazione fattura", MapPin],
  ["history-report", "Report storico", TrendingUp],
  ["ai", "Ask Fatture", Sparkles],
  ["reports", "Report", ChartNoAxesCombined],
  ["history", "Storico", History],
  ["anomalies", "Alert", TriangleAlert],
  ["categories", "Categorie", Tags],
  ["settings", "Impostazioni", Settings],
  ["health", "Salute dati", HeartPulse],
  ["system", "Sistema", MonitorCog],
  ["users", "Utenti", Users],
  ["feedback", "Feedback", MessageSquareWarning],
];
export function Shell({
  page,
  setPage,
  area,
  setArea,
  reviewPage,
  setReviewPage,
  children,
  open,
  setOpen,
  pinned,
  setPinned,
}: {
  page: Page;
  setPage: (p: Page) => void;
  area: "invoices" | "reviews";
  setArea: (a: "invoices" | "reviews") => void;
  reviewPage: "reviews" | "ai";
  setReviewPage: (p: "reviews" | "ai") => void;
  children: ReactNode;
  open: boolean;
  setOpen: (v: boolean) => void;
  pinned: boolean;
  setPinned: (v: boolean) => void;
}) {
  const user = currentUser();
  // Permessi unificati: ogni profilo autenticato ha accesso completo.
  const isFullAccess = Boolean(user);
  const [reviewView, setReviewView] = useState<"overview" | "ranking" | "reviews" | "anonymous" | "anonymous-ranking" | "online" | "history" | "room-averages">("overview");
  const visibleNav = nav.filter(
    ([id]) => (supabaseOnline ? ONLINE_PAGES.includes(id) : id !== "users" && (isFullAccess || !["settings", "system"].includes(id))),
  );
  const online = supabaseOnline;
  const goReview = (view: typeof reviewView) => {
    setReviewPage("reviews");
    setReviewView(view);
    if (online) { setPage("reviews" as Page); setOpen(false); }
    setTimeout(() => window.dispatchEvent(new CustomEvent("eye-review-view", { detail: view })), 60);
  };
  const pickArea = (next: "invoices" | "reviews") => { setArea(next); if (online) { setPage("home"); setOpen(false); } };
  async function logout() {
    try {
      await eyeApi("/auth/logout", { method: "POST" });
    } catch {}
    clearAuth();
    window.dispatchEvent(new Event("eye-auth-expired"));
  }
  return (
    <div className={`app-shell${supabaseOnline ? " online" : ""}`}>
      <aside className={`sidebar ${open ? "open" : ""} ${pinned ? "pinned" : ""}`}>
        <div className="brand">
          <img className="brand-logo" src="/eye-supremo-logo.png" alt="Eye Supremo" />
          <div className="brand-copy"><b>EYE</b><span className="brand-name"> SUPREMO</span><span className="brand-subtitle">Hotel intelligence · {supabaseOnline ? "Online" : "Local first"}</span></div>
        </div>
        <div className="area-switch" role="group" aria-label="Cambia area">
          <button
            className={area === "invoices" ? "active" : ""}
            onClick={() => {
              setArea("invoices");
              setPage("invoices");
            }}
          >
            <ReceiptText />
            Fatture
          </button>
          <button
            className={area === "reviews" ? "active" : ""}
            onClick={() => setArea("reviews")}
          >
            <MessageSquareText />
            Recensioni
          </button>
        </div>
        <div className="sidebar-top-tools" hidden={supabaseOnline}>
          <button className={pinned ? "sidebar-pin active" : "sidebar-pin"} aria-label={pinned ? "Sblocca menu" : "Fissa menu aperto"} title={pinned ? "Sblocca menu" : "Fissa menu aperto"} onClick={() => setPinned(!pinned)}>
            <Pin size={14} /> <span>{pinned ? "Menu fissato" : "Fissa menu"}</span>
          </button>
        </div>
        {area === "invoices" ? (
          <nav>
            {visibleNav.map(([id, label, Icon]) => (
              <button
                key={id}
                aria-label={label}
                className={page === id ? "active" : ""}
                onClick={() => {
                  setPage(id);
                  setOpen(false);
                }}
              >
                <Icon size={19} />
                <span>{label}</span>
              </button>
            ))}
          </nav>
        ) : (
          <nav>
            {([
              ["overview", "Panoramica", LayoutDashboard, true],
              ["ranking", "Ranking", Trophy, true],
              ["room-averages", "Media camere", BedDouble, true],
              ["reviews", "Recensioni", MessageSquareText, true],
              ["anonymous", "Recensioni anonime", MessageSquareWarning, true],
              ["anonymous-ranking", "Ranking anonime", TriangleAlert, true],
              ["online", "Recensioni online", Globe2, false],
              ["history", "Storico recensioni", History, true],
            ] as [typeof reviewView, string, any, boolean][]).filter(([, , , onlineOk]) => !supabaseOnline || onlineOk).map(([view, label, Icon]) => (
              <button
                key={view}
                aria-label={label}
                className={(!supabaseOnline || page === ("reviews" as Page)) && reviewPage === "reviews" && reviewView === view ? "active" : ""}
                onClick={() => {
                  goReview(view);
                  if (view === "ranking") setTimeout(() => document.getElementById("reviews-ranking")?.scrollIntoView({ behavior: "smooth", block: "start" }), 0);
                }}
              >
                <Icon size={19} />
                <span>{label}</span>
              </button>
            ))}
            {!supabaseOnline && (
              <>
                <button aria-label="Analisi IA" className={reviewPage === "ai" ? "active" : ""} onClick={() => setReviewPage("ai")}>
                  <Sparkles size={19} />
                  <span>Analisi IA</span>
                </button>
                <button aria-label="Feedback" className={page === "feedback" ? "active" : ""} onClick={() => { setArea("invoices"); setPage("feedback"); setOpen(false); }}>
                  <MessageSquareWarning size={19} />
                  <span>Feedback</span>
                </button>
                {isFullAccess && (
                  <button aria-label="Impostazioni" onClick={() => { setArea("invoices"); setPage("settings"); }}>
                    <Settings size={19} />
                    <span>Impostazioni</span>
                  </button>
                )}
              </>
            )}
          </nav>
        )}
        <div className="role-box">
          <label>
            <ShieldCheck size={15} />
            {user?.display_name || "Utente"}
          </label>
          <small>Profilo operativo</small>
          <button onClick={logout}>
            <LogOut size={15} />
            Esci
          </button>
        </div>
        {!supabaseOnline && <CacheChip />}
        <div className="local-status">
          <i />
          {supabaseOnline ? <>Archivio centrale<small>Online · sola lettura</small></> : <>Archivio locale<small>Windows · Offline first · Sync opzionale</small></>}
        </div>
      </aside>
      {open && (
        <button
          className="scrim"
          aria-label="Chiudi menu"
          onClick={() => setOpen(false)}
        />
      )}
      {supabaseOnline && (
        <nav className="bottom-bar" aria-label="Navigazione principale">
          {((area === "invoices" ? [
            ["Home", Home, page === "home", () => { setPage("home"); setOpen(false); }],
            ["Fatture", FileText, page === "invoices", () => { setPage("invoices"); setOpen(false); }],
            ["Fornitori", Users, page === "suppliers", () => { setPage("suppliers"); setOpen(false); }],
            ["Prodotti", Package, page === "products", () => { setPage("products"); setOpen(false); }],
          ] : [
            ["Home", Home, page === "home", () => { setPage("home"); setOpen(false); }],
            ["Panoramica", LayoutDashboard, page !== "home" && reviewView === "overview", () => goReview("overview")],
            ["Ranking", Trophy, page !== "home" && reviewView === "ranking", () => goReview("ranking")],
            ["Recensioni", MessageSquareText, page !== "home" && reviewView === "reviews", () => goReview("reviews")],
          ]).concat([["Menu", open ? X : Menu, open, () => setOpen(!open)]]) as [string, any, boolean, () => void][]).map(([label, Icon, active, go]) => (
            <button key={label} className={active ? "active" : ""} aria-current={active ? "page" : undefined} onClick={go}>
              <Icon size={22} />
              <span>{label}</span>
            </button>
          ))}
        </nav>
      )}
      <main>
        {supabaseOnline && (
          <div className="top-switch" role="group" aria-label="Cambia area">
            <button className={area === "invoices" ? "active" : ""} onClick={() => pickArea("invoices")}><ReceiptText size={17} />Fatture</button>
            <button className={area === "reviews" ? "active" : ""} onClick={() => pickArea("reviews")}><MessageSquareText size={17} />Recensioni</button>
          </div>
        )}
        <button className="mobile-menu" onClick={() => setOpen(!open)}>
          {open ? <X /> : <Menu />}
        </button>
        {children}
      </main>
    </div>
  );
}
