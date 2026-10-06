import { useEffect, useState } from "react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  Bell,
  BrainCircuit,
  CalendarDays,
  CircleAlert,
  FileText,
  Package,
  Search,
  Upload,
  WalletCards,
} from "lucide-react";
import { api, eyeApi, euro, shortDate } from "../lib/api";
import { Empty, Loading, PageHeader, Status } from "../components/UI";
import { Page } from "../components/Shell";
type Data = {
  kpis: {
    invoices: number;
    total_spent: number;
    month_spent: number;
    suppliers: number;
    products: number;
  };
  period?: {
    from: string | null;
    to: string | null;
    credit_documents: number;
    credit_total: number;
    latest_month?: string | null;
    latest_month_spent?: number;
  };
  monthly: { month: string; total: number }[];
  annual: { year: string; total: number; invoices: number }[];
  recent: any[];
  anomalies: any[];
};
export default function Dashboard({ go }: { go: (p: Page) => void }) {
  const [data, setData] = useState<Data>();
  const [ollama, setOllama] = useState(false);
  const [showAnnual, setShowAnnual] = useState(false);
  useEffect(() => {
    api<Data>("/dashboard").then(setData);
    api<any>("/ollama/status").then((x) => setOllama(x.available));
  }, []);
  if (!data) return <Loading />;
  const period =
    data.period?.from && data.period?.to
      ? `Archivio ${data.period.from.slice(0, 4)}–${data.period.to.slice(0, 4)}`
      : "Archivio locale aggiornato";
  const monthValue = data.kpis.month_spent || 0;
  const monthLabel = "Questo mese";
  const monthNote = data.kpis.month_spent
    ? "Periodo corrente"
    : "Nessuna fattura nel mese corrente";
  const cards = [
    [FileText, "Fatture", data.kpis.invoices.toLocaleString("it-IT"), period],
    [
      WalletCards,
      "Spesa totale archivio",
      euro(data.kpis.total_spent),
      `${period}${data.period?.credit_documents ? ` · escluse ${data.period.credit_documents} note di credito` : ""}`,
    ],
    [CalendarDays, monthLabel, euro(monthValue), monthNote],
    [
      Package,
      "Prodotti",
      data.kpis.products ? data.kpis.products.toLocaleString("it-IT") : "—",
      data.kpis.products
        ? "Catalogo prodotti centrale"
        : "Catalogo prodotti da indicizzare",
    ],
  ] as const;
  return (
    <>
      <PageHeader
        title="Dashboard"
        subtitle="Panoramica delle tue fatture e analisi acquisti"
      >
        <div className="header-actions">
          <label className="global-search">
            <Search />
            <input
              placeholder="Cerca fatture, prodotti, fornitori…"
              onKeyDown={(e) => {
                if (e.key === "Enter") go("invoices");
              }}
            />
          </label>
          <Bell />
          <div className="ollama">
            <BrainCircuit />
            <i className={ollama ? "online" : ""} />
            <span>
              {ollama ? "Ollama connesso" : "IA locale non disponibile"}
            </span>
          </div>
        </div>
      </PageHeader>
      <section className="kpi-grid">
        {cards.map(([Icon, label, value, small]) => (
          <article
            className={`kpi ${label === "Spesa totale archivio" ? "kpi-clickable" : ""}`}
            key={label}
            onClick={label === "Spesa totale archivio" ? () => setShowAnnual((v) => !v) : undefined}
            onKeyDown={
              label === "Spesa totale archivio"
                ? (e) => e.key === "Enter" && setShowAnnual((v) => !v)
                : undefined
            }
            role={label === "Spesa totale archivio" ? "button" : undefined}
            tabIndex={label === "Spesa totale archivio" ? 0 : undefined}
            title={label === "Spesa totale archivio" ? "Mostra spesa per anno" : undefined}
          >
            <Icon />
            <div>
              <span>{label}</span>
              <strong>{value}</strong>
              <small>{small}</small>
            </div>
          </article>
        ))}
      </section>
      {showAnnual && (
        <section className="panel annual-panel">
          <div className="panel-title">
            <h2>Spesa per anno</h2>
            <button onClick={() => setShowAnnual(false)}>Chiudi</button>
          </div>
          <div className="table-wrap">
            <table>
              <thead>
                <tr><th>Anno</th><th>Fatture</th><th>Totale speso</th></tr>
              </thead>
              <tbody>
                {[...data.annual].reverse().map((item) => (
                  <tr key={item.year}>
                    <td><b>{item.year}</b></td>
                    <td>{item.invoices.toLocaleString("it-IT")}</td>
                    <td><b>{euro(item.total)}</b></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
      <section className="dashboard-grid">
        <article className="panel chart-panel">
          <div className="panel-title">
            <h2>Andamento spesa</h2>
            <span>Ultimi 24 mesi</span>
          </div>
          {data.monthly.length ? (
            <ResponsiveContainer width="100%" height={285}>
              <AreaChart data={data.monthly}>
                <defs>
                  <linearGradient id="fill" x1="0" y1="0" x2="0" y2="1">
                    <stop offset="0" stopColor="#0f8b8d" stopOpacity={0.28} />
                    <stop offset="1" stopColor="#0f8b8d" stopOpacity={0.02} />
                  </linearGradient>
                </defs>
                <CartesianGrid stroke="#e5eaf0" vertical={false} />
                <XAxis dataKey="month" tickLine={false} />
                <YAxis tickLine={false} />
                <Tooltip formatter={(v: any) => euro(v)} />
                <Area
                  type="monotone"
                  dataKey="total"
                  stroke="#0f8b8d"
                  fill="url(#fill)"
                  strokeWidth={2.5}
                />
              </AreaChart>
            </ResponsiveContainer>
          ) : (
            <Empty title="Nessuno storico" />
          )}
        </article>
        <article className="panel quick">
          <h2>Azioni rapide</h2>
          <button onClick={() => go("import")}>
            <Upload />
            <span>
              <b>Importa fatture</b>
              <small>PDF o XML con anteprima</small>
            </span>
          </button>
          <button onClick={() => go("ai")}>
            <BrainCircuit />
            <span>
              <b>Ask Fatture</b>
              <small>Cerca prezzi e fatture reali</small>
            </span>
          </button>
          <div className="quick-note">
            L'app funziona anche senza IA locale.
          </div>
        </article>
      </section>
      <section className="dashboard-grid lower">
        <article className="panel table-panel">
          <div className="panel-title">
            <h2>Fatture recenti</h2>
            <button onClick={() => go("invoices")}>Vedi tutte →</button>
          </div>
          {data.recent.length ? (
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>Numero</th>
                    <th>Data</th>
                    <th>Fornitore</th>
                    <th>Imponibile</th>
                    <th>IVA</th>
                    <th>Totale</th>
                    <th>Stato</th>
                  </tr>
                </thead>
                <tbody>
                  {data.recent.map((i) => (
                    <tr key={i.id}>
                      <td>
                        <b>{i.numero}</b>
                      </td>
                      <td>{shortDate(i.data)}</td>
                      <td>{i.supplier.ragione_sociale}</td>
                      <td>{euro(i.imponibile)}</td>
                      <td>{euro(i.iva)}</td>
                      <td>
                        <b>{euro(i.totale)}</b>
                      </td>
                      <td>
                        <Status>{i.stato_importazione}</Status>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          ) : (
            <Empty />
          )}
        </article>
        <article className="panel alerts">
          <div className="panel-title">
            <h2>Attenzione</h2>
            <button onClick={() => go("anomalies")}>Vedi tutte →</button>
          </div>
          {data.anomalies.length ? (
            data.anomalies.map((a) => (
              <div className="alert-item" key={a.id}>
                <CircleAlert />
                <div>
                  <b>{a.title}</b>
                  <span>{a.description}</span>
                </div>
                <Status tone={a.severity === "high" ? "danger" : "warn"}>
                  {a.severity}
                </Status>
              </div>
            ))
          ) : (
            <Empty title="Tutto in ordine" text="Nessuna anomalia rilevata." />
          )}
        </article>
      </section>
    </>
  );
}
