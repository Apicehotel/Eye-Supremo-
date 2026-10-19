import { Fragment, useEffect, useMemo, useState } from "react";
import { Download, ChevronRight, Bell, Search } from "lucide-react";
import { api, eyeApi, euro, shortDate } from "../lib/api";
import { InvoiceViewer, OpenInvoiceButton, type InvoiceRefTarget } from "../components/InvoiceRef";
import {
  Empty,
  Loading,
  PageHeader,
  SearchBox,
  Status,
} from "../components/UI";
import { Page } from "../components/Shell";
import {useLatestRequest} from "../hooks/useLatestRequest";
import { HistoricalReportPage } from "./HistoricalReport";

import {SortHeader, compareValues, sortIndicator, type SortDirection, type SortKey} from "./lists/TableSort";
export function Reports({ go }: { go: (p: Page) => void }) {
  return (
    <>
      <PageHeader
        title="Report"
        subtitle="Analisi deterministiche ed esportazioni"
      >
        <a className="primary-btn" href="/api/reports/spending.csv">
          <Download size={17} />
          Esporta CSV
        </a>
      </PageHeader>
      <section className="report-grid">
        {[
          "Spesa per mese",
          "Spesa per anno",
          "Spesa per fornitore",
          "Spesa per categoria",
          "Prodotti più acquistati",
          "Aumento prezzi",
          "Confronto fornitori",
          "Duplicati e anomalie",
        ].map((x) => (
          <button
            className="panel report"
            key={x}
            onClick={() =>
              go(
                x.includes("fornitore")
                  ? "suppliers"
                  : x.includes("Prodotti")
                    ? "products"
                    : x.includes("storico")
                      ? "history"
                      : x.includes("Aumento") || x.includes("Duplicati")
                        ? "anomalies"
                        : x.includes("categoria")
                          ? "categories"
                          : "history",
              )
            }
          >
            <div>
              <b>{x}</b>
              <span>Apri sezione analisi</span>
            </div>
            <ChevronRight />
          </button>
        ))}
      </section>
    </>
  );
}
export function HistoryPage() {
  return (
    <>
      <PageHeader
        title="Storico prezzi"
        subtitle="Cerca un prodotto e confronta l’andamento nel tempo per fornitore"
      />
      <section className="panel list-panel history-product-section">
        <HistoricalReportPage embedded />
      </section>
    </>
  );
}

export function AlertsPage() {
  const [items, setItems] = useState<any[]>(),
    [unreadOnly, setUnreadOnly] = useState(false),
    [tracking, setTracking] = useState<Record<string, boolean>>({}),
    [refreshing, setRefreshing] = useState(false),
    [error, setError] = useState(""),
    [permission, setPermission] = useState(
      typeof Notification !== "undefined" ? Notification.permission : "denied",
    );
  async function load() {
    try { setError(""); setItems(await eyeApi<any[]>(`/alerts?unread_only=${unreadOnly}&limit=500`)); }
    catch (e: any) { setError(e.message || "Impossibile caricare gli alert"); }
  }
  useEffect(() => {
    load();
    api<Record<string, boolean>>("/product-tracking").then(setTracking).catch(() => setTracking({}));
    const t = setInterval(load, 30000);
    return () => clearInterval(t);
  }, [unreadOnly]);
  async function refresh() { setRefreshing(true); await load(); setRefreshing(false); }
  async function markRead(id: number | string) {
    if (typeof id !== "number") return;
    try { await eyeApi(`/alerts/${id}/read`, { method: "POST" }); await load(); } catch (e: any) { setError(e.message || "Impossibile aggiornare l'alert"); }
  }
  async function enable() {
    if (typeof Notification === "undefined") return;
    const p = await Notification.requestPermission();
    setPermission(p);
    if (p === "granted")
      new Notification("Eye Supremo", { body: "Notifiche Windows attivate." });
  }
  useEffect(() => {
    if (permission === "granted" && items?.length) {
      const unread = items.find((x) => !x.is_read && !x.resolved);
      if (unread) {
        const key = `eye-alert-${unread.id}`;
        if (!sessionStorage.getItem(key)) {
          new Notification(unread.title, { body: unread.description });
          sessionStorage.setItem(key, "1");
        }
      }
    }
  }, [items, permission]);
  return (
    <>
      <PageHeader
        title="Alert e notifiche"
        subtitle="Aumenti prezzo, anomalie e righe da attenzionare"
      >
        <div className="alert-header-actions"><button className="secondary-btn" onClick={refresh} disabled={refreshing}>{refreshing ? "Aggiorno…" : "Aggiorna"}</button><button className="primary-btn" onClick={enable}><Bell size={17} />{permission === "granted" ? "Notifiche attive" : "Attiva notifiche"}</button></div>
      </PageHeader>
      <section className="panel list-panel">
        <div className="tracked-products"><div><h3>Prezzi monitorati</h3><p>Prodotti selezionati per controllare gli aggiornamenti di prezzo.</p></div><b>{Object.keys(tracking).length}</b></div>
        {Object.keys(tracking).length > 0 && <div className="tracked-product-list">{Object.keys(tracking).map(name => <span key={name}>{name}</span>)}</div>}
        <div className="alerts-toolbar"><div><b>{items?.length ?? 0}</b> alert caricati <span className="alert-unread">{items?.filter(a => !a.is_read && !a.resolved).length ?? 0} non letti</span></div><div className="review-filters"><button className={!unreadOnly ? "active" : ""} onClick={() => setUnreadOnly(false)}>Tutti</button><button className={unreadOnly ? "active" : ""} onClick={() => setUnreadOnly(true)}>Non letti</button></div></div>
        {error ? <div className="error alerts-error">{error}</div> : !items ? (
          <Loading />
        ) : items.length ? (
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Gravità</th>
                  <th>Tipo</th>
                  <th>Alert</th>
                  <th>Descrizione</th>
                  <th>Data</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {items.map((a) => (
                  <tr key={a.id} className={!a.is_read && !a.resolved ? "alert-unread-row" : ""}>
                    <td>
                      <Status
                        tone={
                          a.severity === "high"
                            ? "danger"
                            : a.severity === "warning"
                              ? "warn"
                              : "ok"
                        }
                      >
                        {a.severity}
                      </Status>
                    </td>
                    <td>{a.kind}</td>
                    <td>
                      <b>{a.title}</b>
                    </td>
                    <td>{a.description}</td>
                    <td>{new Date(a.created_at).toLocaleString("it-IT")}</td>
                    <td>{!a.is_read && !a.resolved && typeof a.id === "number" && <button className="alert-read-btn" onClick={() => markRead(a.id)}>Segna letto</button>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : (
          <Empty
            title="Nessun alert"
            text="Eye Supremo controllerà prezzi e anomalie durante le importazioni."
          />
        )}
      </section>
    </>
  );
}

const PRODUCT_CATEGORY_OPTIONS: Record<string, string[]> = {
  "Food & Beverage": ["Colazioni", "Bevande", "Vino", "Cucina", "Dispensa"],
  "Pulizia e igiene": ["Detergenti", "Carta", "Amenities"],
  "Camere e housekeeping": ["Biancheria", "Asciugamani", "Accessori camera"],
  Manutenzione: ["Elettrico", "Idraulica", "Climatizzazione", "Ferramenta"],
  "Arredi e attrezzature": ["Arredi", "Attrezzature cucina", "Attrezzature hotel"],
  "Ufficio e informatica": ["Cancelleria", "Hardware", "Software"],
  Altro: ["Generico"],
  "Da classificare": [],
};

const EXPENSE_CATEGORIES = [
  ["Utenze", "Acqua, luce, gas e telecomunicazioni"],
  ["Trasporti e consegne", "Consegne, corrieri e trasporto merci"],
  ["Carburante", "Benzina, gasolio e rifornimenti"],
  ["Manodopera", "Interventi e prestazioni operative"],
  ["Consulenze", "Servizi professionali e consulenze"],
  ["Canoni e abbonamenti", "Canoni ricorrenti e licenze"],
  ["Commissioni e spese bancarie", "Commissioni, bolli e spese finanziarie"],
  ["Tasse e diritti", "Imposte, diritti e altri oneri"],
] as const;

function suggestedProductCategory(name: string) {
  const value = name.toLowerCase();
  if (/acqua|bevanda|vino|vin[oò]|birra|caffe|caff[eè]|pasta|farina|olio|zuccher|colazion|cadetto/.test(value)) return "Food & Beverage";
  if (/deterg|igien|carta|sapone|shampoo|amenit|disinfett/.test(value)) return "Pulizia e igiene";
  if (/lenzuol|asciugaman|copriletto|cuscino|camera|appendiabiti/.test(value)) return "Camere e housekeeping";
  if (/lampad|elettric|presa|rubinett|tubo|filtro|climat|vernice|vite|bullon/.test(value)) return "Manutenzione";
  if (/sedia|tavol|frigor|forno|attrezz|carrello/.test(value)) return "Arredi e attrezzature";
  if (/carta a4|penna|toner|stampant|computer|mouse|tastier|software/.test(value)) return "Ufficio e informatica";
  return "Da classificare";
}

function suggestedProductSubcategory(name: string, category: string) {
  const value = name.toLowerCase();
  if (category === "Food & Beverage" && /vino|vin[oò]|cadetto|rosso|bianco|binaco|rosato/.test(value)) return "Vino";
  return "";
}

export function CategoriesPage() {
  const [products, setProducts] = useState<any[]>();
  const [configs, setConfigs] = useState<Record<string, any>>({});
  const [drafts, setDrafts] = useState<Record<string, {category: string; subcategory: string}>>({});
  const [q, setQ] = useState("");
  const [filter, setFilter] = useState("all");
  const [saving, setSaving] = useState<string | null>(null);
  const [saved, setSaved] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api<any[]>("/products?q=&limit=200"),
      api<Record<string, any>>("/product-config"),
    ]).then(([items, stored]) => {
      setProducts(items);
      setConfigs(stored);
      const initial: Record<string, {category: string; subcategory: string}> = {};
      items.forEach((item) => {
        const name = item.nome_canonico || item.canonical_name;
        const config = stored[name] || {};
        initial[name] = {
          category: config.category && config.category !== "Da classificare" ? config.category : item.categoria || suggestedProductCategory(name),
          subcategory: config.subcategory || item.sottocategoria || suggestedProductSubcategory(name, config.category || item.categoria || suggestedProductCategory(name)),
        };
      });
      setDrafts(initial);
    }).catch(() => setProducts([]));
  }, []);

  const visible = (products || []).filter((item) => {
    const name = item.nome_canonico || item.canonical_name || "";
    const category = drafts[name]?.category || "Da classificare";
    return name.toLowerCase().includes(q.toLowerCase()) && (filter === "all" || category === filter);
  });

  async function saveCategory(name: string) {
    const draft = drafts[name] || {category: "Da classificare", subcategory: ""};
    const config = configs[name] || {};
    setSaving(name);
    try {
      const result = await api<any>("/product-config", {
        method: "PUT",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify({
          source_name: name,
          configured_name: config.configured_name || name,
          manufacturer: config.manufacturer || "",
          category: draft.category,
          subcategory: draft.subcategory,
        }),
      });
      setConfigs((current) => ({...current, [name]: result}));
      setSaved(name);
      window.setTimeout(() => setSaved((current) => current === name ? null : current), 1800);
    } finally {
      setSaving(null);
    }
  }

  return <>
    <PageHeader title="Categorie" subtitle="Classifica prodotti e spese senza confondere beni, servizi e logistica">
      <div className="list-header-main category-toolbar">
        <SearchBox value={q} onChange={setQ} placeholder="Cerca prodotto…" />
        <select className="review-control" value={filter} onChange={(event) => setFilter(event.target.value)}>
          <option value="all">Tutte le categorie</option>
          {Object.keys(PRODUCT_CATEGORY_OPTIONS).map((category) => <option key={category} value={category}>{category}</option>)}
        </select>
      </div>
    </PageHeader>
    <section className="panel list-panel">
      <div className="panel-title category-panel-title"><div><h2>Prodotti</h2><span>La categoria suggerita può essere corretta e salvata</span></div><Status tone="ok">{visible.length} prodotti</Status></div>
      {!products ? <Loading /> : visible.length ? <div className="table-wrap"><table><thead><tr><th>Prodotto</th><th>Categoria</th><th>Sottocategoria</th><th></th></tr></thead><tbody>
        {visible.map((item) => {
          const name = item.nome_canonico || item.canonical_name;
          const draft = drafts[name] || {category: "Da classificare", subcategory: ""};
          return <tr key={name}><td><b>{configs[name]?.configured_name || name}</b>{draft.category === "Da classificare" && <small className="category-hint">Da verificare</small>}</td><td><select className="category-select" value={draft.category} onChange={(event) => setDrafts((current) => ({...current, [name]: {category: event.target.value, subcategory: ""}}))}>{Object.keys(PRODUCT_CATEGORY_OPTIONS).map((category) => <option key={category}>{category}</option>)}</select></td><td><select className="category-select" value={draft.subcategory} disabled={!PRODUCT_CATEGORY_OPTIONS[draft.category]?.length} onChange={(event) => setDrafts((current) => ({...current, [name]: {...draft, subcategory: event.target.value}}))}><option value="">Nessuna</option>{(PRODUCT_CATEGORY_OPTIONS[draft.category] || []).map((subcategory) => <option key={subcategory}>{subcategory}</option>)}</select></td><td><button className="secondary-btn category-save" disabled={saving === name} onClick={() => saveCategory(name)}>{saving === name ? "Salvo…" : saved === name ? "Salvato" : "Salva"}</button></td></tr>;
        })}
      </tbody></table></div> : <Empty title="Nessun prodotto" text="Importa una fattura XML o cambia il filtro per vedere i prodotti." />}
    </section>
    <section className="panel expense-category-panel"><div className="panel-title"><div><h2>Spese e servizi</h2><span>Restano fuori dal catalogo prodotti ma sono ricercabili nelle fatture e nei fornitori</span></div></div><div className="expense-category-grid">{EXPENSE_CATEGORIES.map(([name, description]) => <article key={name}><b>{name}</b><span>{description}</span></article>)}</div></section>
  </>;
}

export function SimplePage({
  title,
  subtitle,
}: {
  title: string;
  subtitle: string;
}) {
  return (
    <>
      <PageHeader title={title} subtitle={subtitle} />
      <section className="panel list-panel">
        <Empty
          title={`${title} pronto`}
          text="La struttura è disponibile e si popolerà con i dati dell'archivio."
        />
      </section>
    </>
  );
}


export {Invoices} from "./lists/Invoices";
export {Products} from "./lists/Products";
export {Suppliers} from "./lists/Suppliers";
