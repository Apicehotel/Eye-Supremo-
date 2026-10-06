import { ReactNode, useState } from "react";
import {
  LayoutDashboard,
  FileText,
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
} from "lucide-react";
import { clearAuth, currentUser, eyeApi } from "../lib/api";
export type Page =
  | "dashboard"
  | "invoices"
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
  | "feedback";
const nav: [Page, string, any][] = [
  ["dashboard", "Dashboard", LayoutDashboard],
  ["invoices", "Fatture", FileText],
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
  ["system", "Sistema", MonitorCog],
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
  const isDeveloper = user?.role_name === "developer";
  const [reviewView, setReviewView] = useState<"overview" | "ranking" | "reviews">("overview");
  const visibleNav = nav.filter(
    ([id]) => isDeveloper || !["settings", "system"].includes(id),
  );
  async function logout() {
    try {
      await eyeApi("/auth/logout", { method: "POST" });
    } catch {}
    clearAuth();
    window.dispatchEvent(new Event("eye-auth-expired"));
  }
  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? "open" : ""} ${pinned ? "pinned" : ""}`}>
        <div className="brand">
          <img className="brand-logo" src="/eye-supremo-logo.png" alt="Eye Supremo" />
          <div className="brand-copy"><b>EYE</b><span className="brand-name"> SUPREMO</span><span className="brand-subtitle">Hotel intelligence · Local first</span></div>
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
        <div className="sidebar-top-tools">
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
            <button
              aria-label="Panoramica"
              className={reviewPage === "reviews" && reviewView === "overview" ? "active" : ""}
              onClick={() => {
                setReviewPage("reviews");
                setReviewView("overview");
                window.dispatchEvent(
                  new CustomEvent("eye-review-view", { detail: "overview" }),
                );
              }}
            >
              <LayoutDashboard size={19} />
              <span>Panoramica</span>
            </button>
            <button
              aria-label="Ranking"
              className={reviewPage === "reviews" && reviewView === "ranking" ? "active" : ""}
              onClick={() => {
                setReviewPage("reviews");
                setReviewView("ranking");
                window.dispatchEvent(
                  new CustomEvent("eye-review-view", { detail: "ranking" }),
                );
                setTimeout(
                  () =>
                    document
                      .getElementById("reviews-ranking")
                      ?.scrollIntoView({ behavior: "smooth", block: "start" }),
                  0,
                );
              }}
            >
              <Trophy size={19} />
              <span>Ranking</span>
            </button>
            <button
              aria-label="Recensioni"
              className={reviewPage === "reviews" && reviewView === "reviews" ? "active" : ""}
              onClick={() => {
                setReviewPage("reviews");
                setReviewView("reviews");
                window.dispatchEvent(
                  new CustomEvent("eye-review-view", { detail: "reviews" }),
                );
              }}
            >
              <MessageSquareText size={19} />
              <span>Recensioni</span>
            </button>
            <button
              aria-label="Analisi IA"
              className={reviewPage === "ai" ? "active" : ""}
              onClick={() => setReviewPage("ai")}
            >
              <Sparkles size={19} />
              <span>Analisi IA</span>
            </button>
            <button
              aria-label="Feedback"
              className={page === "feedback" ? "active" : ""}
              onClick={() => { setArea("invoices"); setPage("feedback"); setOpen(false); }}
            >
              <MessageSquareWarning size={19} />
              <span>Feedback</span>
            </button>
            {isDeveloper && (
              <button
                aria-label="Impostazioni"
                onClick={() => {
                  setArea("invoices");
                  setPage("settings");
                }}
              >
                <Settings size={19} />
                <span>Impostazioni</span>
              </button>
            )}
          </nav>
        )}
        <div className="role-box">
          <label>
            <ShieldCheck size={15} />
            {user?.display_name || "Utente"}
          </label>
          <small>{user?.role_name || "profilo locale"}</small>
          <button onClick={logout}>
            <LogOut size={15} />
            Esci
          </button>
        </div>
        <div className="local-status">
          <i />
          Archivio locale<small>Windows · Offline first · Sync opzionale</small>
        </div>
      </aside>
      {open && (
        <button
          className="scrim"
          aria-label="Chiudi menu"
          onClick={() => setOpen(false)}
        />
      )}
      <main>
        <button className="mobile-menu" onClick={() => setOpen(!open)}>
          {open ? <X /> : <Menu />}
        </button>
        {children}
      </main>
    </div>
  );
}
