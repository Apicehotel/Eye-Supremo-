import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Database, HardDrive, RefreshCw, Star } from "lucide-react";
import { eyeApi } from "../lib/api";
import { Empty, Loading, PageHeader, Status } from "../components/UI";

type Health = {
  generated_at: string;
  local_records: Record<string, number>;
  synchronized: { total: number; reviews: number; invoices: number };
  sync: { queued: number; conflicts: number; supabase_configured: boolean };
  imports: { errors: number; latest_errors: { message: string; created_at: string | null }[] };
  reviews: { without_room: number; without_rating: number };
  last_sync: { invoices: string | null; reviews: string | null };
  backups: { count: number; latest: { message: string; created_at: string | null }[] };
};

function when(value: string | null | undefined) {
  return value ? new Date(value).toLocaleString("it-IT") : "Mai rilevato";
}

export default function DataHealth() {
  const [data, setData] = useState<Health>();
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  async function load() {
    setBusy(true);
    try { setData(await eyeApi<Health>("/data-health")); setError(""); }
    catch (e) { setError(e instanceof Error ? e.message : "Salute dati non disponibile"); }
    finally { setBusy(false); }
  }
  useEffect(() => { load(); }, []);
  if (error) return <section className="panel" role="alert"><p>{error}</p><button className="primary-btn" onClick={load}>Riprova</button></section>;
  if (!data) return <Loading />;
  const local = data.local_records;
  return <>
    <PageHeader title="Salute dati" subtitle="Controllo trasparente dell’archivio locale, degli import e della sincronizzazione">
      <button className="secondary-btn" onClick={load} disabled={busy}><RefreshCw size={15} />{busy ? "Aggiornamento…" : "Aggiorna"}</button>
    </PageHeader>
    <section className="data-health-grid">
      <article className="kpi"><Database /><div><span>Record locali</span><strong>{local.total.toLocaleString("it-IT")}</strong><small>fatture, righe, prodotti, fornitori e recensioni valide</small></div></article>
      <article className="kpi"><CheckCircle2 /><div><span>Record sincronizzati</span><strong>{data.synchronized.total.toLocaleString("it-IT")}</strong><small>{data.synchronized.reviews} recensioni · {data.synchronized.invoices} fatture</small></div></article>
      <article className="kpi"><HardDrive /><div><span>Coda locale</span><strong>{data.sync.queued}</strong><small>{data.sync.supabase_configured ? "in attesa o da verificare" : "Supabase non indispensabile"}</small></div></article>
      <article className="kpi"><AlertTriangle /><div><span>Errori import / conflitti</span><strong>{data.imports.errors} / {data.sync.conflicts}</strong><small>richiedono controllo</small></div></article>
    </section>
    <section className="dashboard-grid data-health-columns">
      <article className="panel"><div className="panel-title"><h2>Archivio locale</h2><Status tone="ok">Fonte PC</Status></div><div className="health-list"><div><span>Fatture</span><b>{local.invoices}</b></div><div><span>Righe fattura</span><b>{local.invoice_rows}</b></div><div><span>Prodotti</span><b>{local.products}</b></div><div><span>Fornitori</span><b>{local.suppliers}</b></div><div><span>Recensioni grezze</span><b>{local.reviews_raw}</b></div><div><span>Recensioni valide</span><b>{local.reviews_valid}</b></div></div></article>
      <article className="panel"><div className="panel-title"><h2>Recensioni da completare</h2><Status tone={data.reviews.without_room || data.reviews.without_rating ? "warn" : "ok"}>{data.reviews.without_room || data.reviews.without_rating ? "Da verificare" : "Completo"}</Status></div><div className="health-list"><div><span>Senza camera</span><b>{data.reviews.without_room}</b></div><div><span>Senza voto</span><b>{data.reviews.without_rating}</b></div></div><p className="health-note">Questi record restano disponibili, ma sono esclusi solo dalle analisi che richiedono quel campo.</p></article>
    </section>
    <section className="dashboard-grid data-health-columns">
      <article className="panel"><div className="panel-title"><h2>Ultimi sync</h2><Status tone={data.sync.supabase_configured ? "ok" : "warn"}>{data.sync.supabase_configured ? "Supabase attivo" : "Solo locale"}</Status></div><div className="health-list"><div><span>Fatture</span><b>{when(data.last_sync.invoices)}</b></div><div><span>Recensioni</span><b>{when(data.last_sync.reviews)}</b></div></div></article>
      <article className="panel"><div className="panel-title"><h2>Ultimi backup</h2><HardDrive size={18} /></div>{data.backups.latest.length ? <div className="health-events">{data.backups.latest.map((item, index) => <div key={`${item.created_at}-${index}`}><b>{when(item.created_at)}</b><span>{item.message}</span></div>)}</div> : <Empty title="Nessun backup registrato" text="Crea il primo backup dalla sezione Impostazioni." />}</article>
    </section>
    <section className="panel"><div className="panel-title"><h2>Errori import recenti</h2><Status tone={data.imports.errors ? "warn" : "ok"}>{data.imports.errors}</Status></div>{data.imports.latest_errors.length ? <div className="health-events">{data.imports.latest_errors.map((item, index) => <div key={`${item.created_at}-${index}`}><b>{when(item.created_at)}</b><span>{item.message}</span></div>)}</div> : <Empty title="Nessun errore recente" text="Gli import registrati risultano completati." />}</section>
  </>;
}
