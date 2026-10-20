import { useCallback, useEffect, useState } from "react";
import { eyeApi } from "../lib/api";

export type CacheHealth = "ok" | "unverified" | "syncing" | "incomplete" | "empty" | "error" | "not_configured";

export type CacheBootstrap = {
  health: CacheHealth;
  headline: string;
  running: boolean;
  ready_offline: boolean;
  configured: boolean;
  completed_at?: string | null;
  detail?: string;
  invoices?: { count: number; remote_total?: number | null; percent?: number | null; missing?: number | null };
  reviews?: { count: number };
  progress?: { downloaded?: number; total?: number } | null;
};

const fmt = (n?: number | null) => (n ?? 0).toLocaleString("it-IT");

const TONE: Record<CacheHealth, { cls: string; label: string }> = {
  ok: { cls: "ok", label: "Offline pronto" },
  unverified: { cls: "warn", label: "Da verificare" },
  syncing: { cls: "sync", label: "Download in corso" },
  incomplete: { cls: "warn", label: "Incompleta" },
  empty: { cls: "danger", label: "Vuota" },
  error: { cls: "danger", label: "Errore" },
  not_configured: { cls: "muted", label: "Non configurata" },
};

export function useCacheStatus() {
  const [data, setData] = useState<CacheBootstrap>();
  const reload = useCallback(
    () => eyeApi<CacheBootstrap>("/cache/bootstrap/status").then(setData).catch(() => undefined),
    [],
  );
  useEffect(() => {
    reload();
  }, [reload]);
  useEffect(() => {
    const timer = window.setInterval(reload, data?.running ? 3000 : 60000);
    return () => window.clearInterval(timer);
  }, [reload, data?.running]);
  return { data, reload };
}

/** Indicatore compatto sempre visibile (barra laterale). */
export function CacheChip() {
  const { data } = useCacheStatus();
  if (!data) return null;
  const tone = TONE[data.health] ?? TONE.empty;
  const inv = data.invoices;
  const short =
    data.health === "syncing"
      ? `${fmt(data.progress?.downloaded ?? inv?.count)}${inv?.remote_total ? ` / ${fmt(inv.remote_total)}` : ""}`
      : data.health === "incomplete" && inv?.remote_total
        ? `${fmt(inv.count)} / ${fmt(inv.remote_total)}`
        : `${fmt(inv?.count)} fatture`;
  return (
    <div className={`cache-chip ${tone.cls}`} title={data.headline}>
      <i />
      <b>{tone.label}</b>
      <small>{short}</small>
    </div>
  );
}

/** Scheda di stato a colpo d'occhio (Dashboard). */
export function CacheStatusCard() {
  const { data, reload } = useCacheStatus();
  const [busy, setBusy] = useState(false);
  if (!data) return null;
  const tone = TONE[data.health] ?? TONE.empty;
  const inv = data.invoices;
  const pct = inv?.percent ?? (data.health === "ok" ? 100 : null);
  const canFix = data.configured && !data.running && data.health !== "ok";

  async function start() {
    setBusy(true);
    try {
      await eyeApi("/cache/bootstrap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ background: true, full: data?.health === "incomplete" }),
      });
      await reload();
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className={`panel cache-card ${tone.cls}`} aria-live="polite">
      <div className="cache-card-head">
        <span className="cache-dot" />
        <div>
          <strong>{data.headline}</strong>
          <small>
            Recensioni in cache: {fmt(data.reviews?.count)}
            {data.completed_at ? ` · ultimo aggiornamento ${new Date(data.completed_at).toLocaleString("it-IT")}` : ""}
          </small>
        </div>
        {canFix && (
          <button className="primary-btn" disabled={busy} onClick={start}>
            {busy ? "Avvio…" : data.health === "incomplete" ? "Completa download" : "Scarica ora"}
          </button>
        )}
      </div>
      {pct !== null && (
        <div className="cache-bar" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct}>
          <div style={{ width: `${pct}%` }} />
        </div>
      )}
      {inv?.remote_total ? (
        <small className="cache-numbers">
          {fmt(inv.count)} di {fmt(inv.remote_total)} fatture
          {inv.missing ? ` · mancano ${fmt(inv.missing)}` : ""}
        </small>
      ) : null}
      {data.detail && data.health !== "ok" && <small className="cache-detail">{data.detail}</small>}
    </section>
  );
}
