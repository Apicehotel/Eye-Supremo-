import { useEffect, useRef, useState } from "react";
import {
  UploadCloud,
  FileCheck,
  BrainCircuit,
  DatabaseBackup,
  Download,
  RefreshCw,
} from "lucide-react";
import {
  api,
  currentRole,
  currentSession,
  currentUser,
  eyeApi,
  euro,
} from "../lib/api";
import { Empty, PageHeader, Status } from "../components/UI";
import { UserAdmin } from "../components/UserAdmin";

type Hotel = { id: number; code: string; name: string };
type BatchItem = {
  filename: string;
  ok: boolean;
  error?: string;
  preview?: any;
  confirmed?: boolean;
  confirmError?: string;
  result?: any;
};

export function ImportPage() {
  const input = useRef<HTMLInputElement>(null),
    [busy, setBusy] = useState(false),
    [items, setItems] = useState<BatchItem[]>([]),
    [selectedJob, setSelectedJob] = useState<number | undefined>(),
    [error, setError] = useState(""),
    [done, setDone] = useState("");
  const preview = items.find(
    (x) => x.ok && x.preview?.job_id === selectedJob,
  )?.preview;
  const ready = items.filter((x) => x.ok && !x.confirmed).length;
  const confirmed = items.filter((x) => x.confirmed).length;
  const failed = items.filter((x) => !x.ok || x.confirmError).length;

  async function upload(files: File[]) {
    if (!files.length) return;
    setBusy(true);
    setError("");
    setDone("");
    setItems([]);
    setSelectedJob(undefined);
    const body = new FormData();
    files.forEach((file) => body.append("files", file));
    try {
      const headers: Record<string, string> = { "X-Eye-Role": currentRole() };
      if (currentSession()) headers["X-Eye-Session"] = currentSession();
      const res = await fetch("/api/eye/invoices/import/preview-batch", {
        method: "POST",
        headers,
        body,
      });
      if (!res.ok) throw new Error(await res.text());
      const result = await res.json();
      const batch: BatchItem[] = result.items || [];
      setItems(batch);
      const first = batch.find((x) => x.ok && x.preview);
      if (first) setSelectedJob(first.preview.job_id);
      setDone(
        `${result.ready} fatture pronte${result.failed ? ` · ${result.failed} file scartati` : ""}`,
      );
    } catch (e: any) {
      setError(e.message);
    } finally {
      setBusy(false);
      if (input.current) input.current.value = "";
    }
  }

  async function confirmOne(index: number) {
    const item = items[index];
    if (!item?.ok || !item.preview || item.confirmed) return;
    try {
      const result: any = await eyeApi(
        `/invoices/import/${item.preview.job_id}/confirm`,
        {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: "{}",
        },
      );
      setItems((current) =>
        current.map((x, i) =>
          i === index
            ? { ...x, confirmed: true, confirmError: undefined, result }
            : x,
        ),
      );
      return true;
    } catch (e: any) {
      setItems((current) =>
        current.map((x, i) =>
          i === index ? { ...x, confirmError: e.message } : x,
        ),
      );
      return false;
    }
  }

  async function confirmAll() {
    setBusy(true);
    setError("");
    let ok = 0,
      bad = 0;
    for (let i = 0; i < items.length; i++) {
      if (items[i].ok && !items[i].confirmed) {
        (await confirmOne(i)) ? ok++ : bad++;
      }
    }
    setDone(`${ok} fatture salvate${bad ? ` · ${bad} da verificare` : ""}`);
    setBusy(false);
  }

  return (
    <>
      <PageHeader
        title="Importa fatture"
        subtitle="Archivio unico Apice · multi-file e ZIP · massimo 100 fatture per lotto"
      />
      <section className="import-layout">
        <article
          className="panel dropzone"
          onClick={() => input.current?.click()}
          onDragOver={(e) => e.preventDefault()}
          onDrop={(e) => {
            e.preventDefault();
            upload(Array.from(e.dataTransfer.files));
          }}
        >
          <UploadCloud />
          <h2>
            {busy ? "Operazione in corso…" : "Trascina qui fatture o uno ZIP"}
          </h2>
          <p>
            Puoi selezionare più XML/TXT/PDF insieme oppure uno ZIP. Eye Supremo
            estrae e analizza fino a 100 fatture per lotto.
          </p>
          <p>XML FatturaPA, TXT, PDF · massimo 100 MB per file</p>
          <p>
            ZIP · massimo 120 MB · massimo 200 MB estratti · fino a 100 fatture
          </p>
          <button className="primary-btn">Seleziona file</button>
          <input
            ref={input}
            hidden
            multiple
            type="file"
            accept=".xml,.txt,.pdf,.zip"
            onChange={(e) => upload(Array.from(e.target.files || []))}
          />
          {error && <div className="error">{error}</div>}
          {done && <div className="success">{done}</div>}
        </article>

        {items.length > 0 ? (
          <article className="panel preview">
            <div className="panel-title">
              <h2>Lotto importazione</h2>
              <Status tone={failed ? "warn" : "ok"}>
                {confirmed}/{items.length} salvate
              </Status>
            </div>
            <div className="form-actions">
              <button
                className="primary-btn"
                disabled={busy || ready === 0}
                onClick={confirmAll}
              >
                <FileCheck />
                Conferma tutte ({ready})
              </button>
            </div>
            <div className="table-wrap">
              <table>
                <thead>
                  <tr>
                    <th>File</th>
                    <th>Stato</th>
                    <th>Fornitore</th>
                    <th>Totale</th>
                    <th>Azione</th>
                  </tr>
                </thead>
                <tbody>
                  {items.map((item, i) => (
                    <tr
                      key={`${item.filename}-${i}`}
                      className={
                        item.preview?.job_id === selectedJob ? "active-row" : ""
                      }
                      onClick={() =>
                        item.preview && setSelectedJob(item.preview.job_id)
                      }
                    >
                      <td>{item.filename}</td>
                      <td>
                        {item.confirmed ? (
                          <Status tone="ok">Salvata</Status>
                        ) : item.confirmError ? (
                          <Status tone="danger">Da verificare</Status>
                        ) : item.ok ? (
                          <Status tone="ok">Pronta</Status>
                        ) : (
                          <Status tone="danger">Scartata</Status>
                        )}
                      </td>
                      <td>
                        {item.preview?.supplier?.ragione_sociale ||
                          item.error ||
                          item.confirmError ||
                          "—"}
                      </td>
                      <td>
                        {item.preview?.invoice?.totale != null
                          ? euro(Number(item.preview.invoice.totale))
                          : "—"}
                      </td>
                      <td>
                        {item.ok && !item.confirmed && (
                          <button
                            className="secondary-btn"
                            disabled={busy}
                            onClick={(e) => {
                              e.stopPropagation();
                              confirmOne(i);
                            }}
                          >
                            Conferma
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </article>
        ) : (
          <article className="panel preview">
            <Empty
              title="Import multiplo"
              text="Seleziona fino a 100 fatture oppure uno ZIP. I file non supportati vengono scartati senza bloccare il resto del lotto."
            />
          </article>
        )}
      </section>

      {preview && (
        <section className="panel preview" style={{ marginTop: 16 }}>
          <div className="panel-title">
            <h2>Anteprima · {preview.filename}</h2>
            <Status tone={preview.confidence > 0.8 ? "ok" : "warn"}>
              {Math.round(preview.confidence * 100)}% confidenza
            </Status>
          </div>
          <div className="preview-grid">
            <label>
              Fornitore
              <input readOnly value={preview.supplier.ragione_sociale || ""} />
            </label>
            <label>
              Numero
              <input readOnly value={preview.invoice.numero || ""} />
            </label>
            <label>
              Data
              <input readOnly type="date" value={preview.invoice.data || ""} />
            </label>
            <label>
              Totale
              <input readOnly value={preview.invoice.totale ?? ""} />
            </label>
          </div>
          {preview.duplicate_matches?.length > 0 && (
            <div className="warning">
              Possibile duplicato: #{preview.duplicate_matches.join(", #")}
            </div>
          )}
          <h3>{preview.rows.length} righe rilevate</h3>
          <div className="table-wrap">
            <table>
              <thead>
                <tr>
                  <th>Descrizione</th>
                  <th>Quantità</th>
                  <th>Unità</th>
                  <th>Prezzo</th>
                  <th>Confidenza</th>
                </tr>
              </thead>
              <tbody>
                {preview.rows.map((r: any, i: number) => (
                  <tr key={i}>
                    <td>{r.descrizione_originale}</td>
                    <td>{r.quantita}</td>
                    <td>{r.unita_originale || "—"}</td>
                    <td>{euro(Number(r.prezzo_unitario))}</td>
                    <td>{Math.round(r.confidence * 100)}%</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </>
  );
}

export function AIPage({ reviewOnly = false }: { reviewOnly?: boolean }) {
  const [q, setQ] = useState(""),
    [answer, setAnswer] = useState<any>(),
    [busy, setBusy] = useState(false),
    [hotel, setHotel] = useState(""),
    [hotels, setHotels] = useState<Hotel[]>([]);
  const askAbort = useRef<AbortController | null>(null);
  useEffect(() => {
    eyeApi<Hotel[]>("/hotels").then(setHotels);
    return () => askAbort.current?.abort();
  }, []);
  async function ask() {
    if (!q.trim() || busy) return;
    askAbort.current?.abort();
    const controller = new AbortController();
    askAbort.current = controller;
    setBusy(true);
    try {
      setAnswer(
        await eyeApi("/agents/ask", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ question: q, hotel_code: hotel || undefined }),
          signal: controller.signal,
        }),
      );
    } catch (error: any) {
      if (error?.name === "AbortError") return;
      setAnswer({
        mode: "orchestrated-deterministic",
        answer: error?.message || "Richiesta non riuscita",
        ai_layer: "deterministic",
      });
    } finally {
      if (askAbort.current === controller) askAbort.current = null;
      setBusy(false);
    }
  }
  const examples = reviewOnly
    ? [
        "Quali sono le 5 camere migliori?",
        "Quali servizi hanno più problemi?",
        "Qual è il sentiment del Giò?",
        "Confronta le recensioni degli hotel",
      ]
    : [
        "Qual è la fattura con il totale più alto?",
        "Chi mi vende meglio i bomboloni?",
        "Quanto è aumentata l’acqua naturale?",
        "Confronta il prezzo di un prodotto tra i fornitori",
      ];
  const invoiceRows = answer?.context?.invoice_rows || [];
  return (
    <>
      <PageHeader
        title={reviewOnly ? "Analisi IA recensioni" : "Ask Fatture"}
        subtitle={
          reviewOnly
            ? "Analisi separata di recensioni, camere, servizi e ranking"
            : "Cerca fatture, prodotti, fornitori e prezzi nell’archivio locale"
        }
      >
        {reviewOnly && (
          <select value={hotel} onChange={(e) => setHotel(e.target.value)}>
            <option value="">Tutti gli hotel</option>
            {hotels.map((h) => (
              <option key={h.code} value={h.code}>
                {h.name}
              </option>
            ))}
          </select>
        )}
      </PageHeader>
      <section className="ai-layout">
        <article className="panel ai-hero">
          <BrainCircuit />
          <h2>Cosa vuoi sapere?</h2>
          <div className="ask-box">
            <textarea
              value={q}
              onChange={(e) => setQ(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === "Enter" && !e.shiftKey) {
                  e.preventDefault();
                  void ask();
                }
              }}
              placeholder={
                reviewOnly
                  ? "Es. Quali sono le camere peggiori del Giò?"
                  : "Es. Qual è la fattura con il totale più alto? Chi mi vende meglio i bomboloni?"
              }
            />
            <button className="primary-btn" onClick={ask}>
              {busy ? "Agenti al lavoro…" : "Chiedi"}
            </button>
          </div>
          <div className="examples">
            {examples.map((x) => (
              <button onClick={() => setQ(x)} key={x}>
                {x}
              </button>
            ))}
          </div>
        </article>
        {answer && (
          <article className="panel ai-answer">
            <div className="panel-title">
              <h2>Risposta</h2>
              <Status
                tone={answer.mode === "orchestrated-ollama" ? "ok" : "warn"}
              >
                {answer.mode === "orchestrated-ollama"
                  ? answer.ai_layer === "fast"
                    ? "Layer veloce"
                    : answer.ai_layer === "quality"
                      ? "Layer qualità"
                      : "IA + agenti"
                  : "Agenti locali"}
              </Status>
            </div>
            <p>{answer.answer}</p>
            {answer.agents?.length > 0 && (
              <small>
                Agenti: {answer.agents.map((a: any) => a.name).join(" → ")}
                {answer.ai_model ? ` · modello ${answer.ai_model}` : ""}
              </small>
            )}
            {answer.verification?.warnings?.map((w: string) => (
              <div className="warning" key={w}>
                {w}
              </div>
            ))}
            {answer.context?.invoice_summary && (
              <small>
                Righe pertinenti: {answer.context.invoice_summary.rows} · Totale
                righe: {euro(answer.context.invoice_summary.row_total)}
              </small>
            )}
            {invoiceRows.length > 0 && (
              <div className="table-wrap" style={{ marginTop: 16 }}>
                <h3>Dati verificati</h3>
                <table>
                  <thead>
                    <tr>
                      <th>Prodotto</th>
                      <th>Fornitore</th>
                      <th>Data</th>
                      <th>Quantità</th>
                      <th>Prezzo unit.</th>
                      <th>Prezzo normalizzato</th>
                      <th>Totale</th>
                    </tr>
                  </thead>
                  <tbody>
                    {invoiceRows.map((r: any, i: number) => (
                      <tr key={`${r.row_id || r.invoice_id}-${i}`}>
                        <td>
                          <b>{r.description || "—"}</b>
                        </td>
                        <td>{r.supplier || "—"}</td>
                        <td>{r.date || "—"}</td>
                        <td>
                          {r.quantity ?? "—"} {r.unit || ""}
                        </td>
                        <td>
                          {r.unit_price != null
                            ? euro(Number(r.unit_price))
                            : "—"}
                        </td>
                        <td>
                          {r.normalized_price != null
                            ? `${euro(Number(r.normalized_price))} / ${r.unit || "unità"}`
                            : "Non disponibile"}
                        </td>
                        <td>
                          {r.row_total != null
                            ? euro(Number(r.row_total))
                            : "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </article>
        )}
      </section>
    </>
  );
}

export function SettingsPage() {
  const user = currentUser();
  const canManage = user?.role_name === "developer" || user?.role_name === "supremo";
  const [data, setData] = useState<any>(),
    [status, setStatus] = useState<any>(),
    [sync, setSync] = useState<any>(),
    [centralSync, setCentralSync] = useState<any>(),
    [bootstrap, setBootstrap] = useState<any>(),
    [syncBusy, setSyncBusy] = useState(false),
    [syncError, setSyncError] = useState(""),
    [hotels, setHotels] = useState<Hotel[]>([]),
    [activeTab, setActiveTab] = useState("IA locale");
  useEffect(() => {
    if (canManage) {
      api("/settings").then(setData);
      api("/ollama/status").then(setStatus);
      loadSyncStatus();
      eyeApi<Hotel[]>("/hotels").then(setHotels).catch(() => setHotels([]));
    }
  }, []);
  useEffect(() => {
    if (!canManage || !bootstrap?.running) return;
    const timer = window.setInterval(() => {
      eyeApi<any>("/cache/bootstrap/status").then(setBootstrap).catch(() => undefined);
    }, 2500);
    return () => window.clearInterval(timer);
  }, [canManage, bootstrap?.running]);
  if (!canManage)
    return (
      <>
        <PageHeader
          title="Impostazioni"
          subtitle="Area gestione locale"
        />
        <section className="panel">
          <Empty
            title="Accesso riservato"
            text="Il profilo corrente non può modificare configurazione, utenti o backup."
          />
        </section>
      </>
    );
  async function save() {
    await api("/settings", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(data),
    });
    alert("Impostazioni salvate");
  }
  async function backup() {
    const r: any = await api("/backups", { method: "POST" });
    alert(`Backup creato: ${r.filename}`);
  }
  async function loadSyncStatus() {
    try {
      const [bridge, central, boot] = await Promise.all([
        eyeApi<any>("/sync/status"),
        eyeApi<any>("/central/sync/status"),
        eyeApi<any>("/cache/bootstrap/status"),
      ]);
      setSync(bridge);
      setCentralSync(central);
      setBootstrap(boot);
      setSyncError("");
    } catch (error: any) {
      setSyncError(error.message || "Stato sincronizzazione non disponibile");
    }
  }
  async function refreshCentralCache() {
    setSyncBusy(true);
    setSyncError("");
    try {
      await eyeApi("/central/sync", { method: "POST" });
      await loadSyncStatus();
    } catch (error: any) {
      setSyncError(error.message || "Aggiornamento cache non riuscito");
    } finally {
      setSyncBusy(false);
    }
  }
  async function downloadOfflineCache(full = false) {
    setSyncBusy(true);
    setSyncError("");
    try {
      const boot = await eyeApi<any>("/cache/bootstrap", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ background: true, full }),
      });
      setBootstrap(boot);
      await loadSyncStatus();
    } catch (error: any) {
      setSyncError(error.message || "Download cache offline non riuscito");
    } finally {
      setSyncBusy(false);
    }
  }
  const tabs = [
    "Generali",
    "Hotel",
    "Utenti e ruoli",
    "Esclusioni fatture",
    "IA locale",
    "Sincronizzazione",
    "Backup",
    "Sicurezza",
  ];
  return (
    <>
      <PageHeader
        title="Impostazioni"
        subtitle="Utenti, IA locale, sincronizzazione, backup e sicurezza"
      />
      <div className="settings-layout">
        <aside className="settings-nav">
          {tabs.map((x) => (
            <button
              className={activeTab === x ? "active" : ""}
              key={x}
              onClick={() => setActiveTab(x)}
            >
              {x}
            </button>
          ))}
        </aside>
        <section className="panel settings-form">
          <div className="panel-title">
            <h2>{activeTab}</h2>
            <Status
              tone={
                activeTab === "IA locale" && status?.available ? "ok" : "warn"
              }
            >
              {activeTab === "IA locale"
                ? status?.available
                  ? "Connesso"
                  : "Non disponibile"
                : "Sezione pronta"}
            </Status>
          </div>
          {activeTab === "Utenti e ruoli" && <UserAdmin />}
          {activeTab === "Hotel" && (
            <>
              <p>Hotel disponibili per la destinazione delle fatture e per le recensioni.</p>
              {hotels.length ? <div className="settings-hotel-list">{hotels.map((hotel) => <div key={hotel.id}><b>{hotel.name}</b><span>{hotel.code}</span></div>)}</div> : <Empty title="Nessun hotel configurato" text="Gli hotel compariranno qui quando saranno disponibili nell’archivio locale." />}
            </>
          )}
          {activeTab === "Generali" && data && (
            <>
              <label>Dimensione massima importazione<input value={`${data.max_upload_mb} MB`} readOnly /></label>
              <label>Tema interfaccia<select value={data.theme || "zenify"} onChange={(e) => setData({...data, theme: e.target.value})}><option value="zenify">Zenify arancio</option><option value="classic">Classico blu</option></select></label>
              <div className="form-actions"><button className="primary-btn" onClick={save}>Salva</button></div>
            </>
          )}
          {activeTab === "IA locale" && data && (
            <>
              <p>
                Layer mirror: il PC usa prima un modello veloce; la qualità interviene solo se serve.
                I calcoli restano sempre su SQLite locale.
              </p>
              <label>
                URL Ollama
                <input
                  value={data.ollama_url}
                  onChange={(e) =>
                    setData({ ...data, ollama_url: e.target.value })
                  }
                />
              </label>
              <label>
                Policy layer
                <select
                  value={data.ai_layer_policy || "fast_first"}
                  onChange={(e) =>
                    setData({ ...data, ai_layer_policy: e.target.value })
                  }
                >
                  <option value="fast_first">Veloce prima (PC ufficio)</option>
                  <option value="fast_only">Solo veloce</option>
                  <option value="quality">Solo qualità</option>
                </select>
              </label>
              <label>
                Modello veloce (mirror)
                <input
                  value={data.chat_model_fast || "llama3.2:3b"}
                  onChange={(e) =>
                    setData({ ...data, chat_model_fast: e.target.value })
                  }
                  placeholder="llama3.2:3b"
                />
              </label>
              <label>
                Modello qualità
                <input
                  value={data.chat_model}
                  onChange={(e) =>
                    setData({ ...data, chat_model: e.target.value })
                  }
                  placeholder="qwen3:8b"
                />
              </label>
              <label>
                Modello embedding
                <input
                  value={data.embedding_model}
                  onChange={(e) =>
                    setData({ ...data, embedding_model: e.target.value })
                  }
                />
              </label>
              {status?.layers && (
                <p className="settings-message">
                  Sequenza attiva:{" "}
                  {(status.layers.active_sequence || [])
                    .map((x: { layer: string; model: string }) => `${x.layer}→${x.model}`)
                    .join(" · ") || "nessun modello trovato"}
                </p>
              )}
              <div className="form-actions">
                <button
                  className="secondary-btn"
                  onClick={() => api("/ollama/status").then(setStatus)}
                >
                  <RefreshCw />
                  Test IA
                </button>
                <button className="primary-btn" onClick={save}>
                  Salva
                </button>
              </div>
            </>
          )}
          {activeTab === "Esclusioni fatture" && <Empty title="Esclusioni fatture" text="Le righe di servizio, consegna, carburante e altre spese non prodotto restano ricercabili senza entrare nel catalogo prodotti." />}
          {activeTab === "Sincronizzazione" && (
            <div className="sync-settings">
              <div className="sync-status-grid">
                <article>
                  <span>Ponte push-pull</span>
                  <b>{sync?.enabled && sync?.configured ? "Configurato" : "Non configurato"}</b>
                  <small>{sync?.mode || "local-first"}</small>
                </article>
                <article>
                  <span>Cache fatture</span>
                  <b>{bootstrap?.invoices?.count ?? centralSync?.count ?? "—"}</b>
                  <small>{bootstrap?.invoices?.state || centralSync?.state || "mai aggiornata"}</small>
                </article>
                <article>
                  <span>Cache recensioni</span>
                  <b>{bootstrap?.reviews?.count ?? "—"}</b>
                  <small>{bootstrap?.reviews?.state || "mai aggiornata"}</small>
                </article>
                <article>
                  <span>Bootstrap offline</span>
                  <b>
                    {bootstrap?.running
                      ? "In corso"
                      : bootstrap?.ready_offline
                        ? "Pronta"
                        : bootstrap?.state || "Mai"}
                  </b>
                  <small>
                    {bootstrap?.completed_at
                      ? new Date(bootstrap.completed_at).toLocaleString("it-IT")
                      : "Supabase → PC"}
                  </small>
                </article>
              </div>
              <p>
                Alla prima installazione Eye Supremo scarica automaticamente fatture e recensioni
                nella cache del PC. Offline userà solo questi dati già scaricati.
              </p>
              {bootstrap?.detail && <p className="settings-message">{bootstrap.detail}</p>}
              {syncError && <div className="error">{syncError}</div>}
              <div className="form-actions">
                <button className="secondary-btn" onClick={loadSyncStatus} disabled={syncBusy}>
                  <RefreshCw size={15} />
                  Aggiorna stato
                </button>
                <button
                  className="secondary-btn"
                  onClick={refreshCentralCache}
                  disabled={syncBusy || !centralSync?.configured}
                >
                  <RefreshCw size={15} />
                  Solo fatture
                </button>
                <button
                  className="primary-btn"
                  onClick={() => downloadOfflineCache(true)}
                  disabled={syncBusy || !bootstrap?.configured}
                >
                  <Download size={15} />
                  {bootstrap?.running || syncBusy
                    ? "Download in corso…"
                    : "Scarica tutto per offline"}
                </button>
              </div>
            </div>
          )}
          {activeTab === "Backup" && <><p>Crea una copia locale del database e delle configurazioni correnti.</p><button className="secondary-btn" onClick={backup}><DatabaseBackup />Crea backup ora</button></>}
          {activeTab === "Sicurezza" && <Empty title="Accesso locale" text="Gli utenti accedono con PIN locale. Sviluppatore e Supremo hanno attualmente lo stesso livello operativo." />}
        </section>
      </div>
    </>
  );
}

export function SystemPage() {
  const user = currentUser();
  const canManage = user?.role_name === "developer" || user?.role_name === "supremo";
  const [logs, setLogs] = useState<any[]>();
  const [update, setUpdate] = useState<any>();
  const [updateBusy, setUpdateBusy] = useState(false);
  const [updateError, setUpdateError] = useState("");
  async function checkForUpdate() {
    setUpdateBusy(true); setUpdateError("");
    try { setUpdate(await eyeApi<any>("/updates/check")); }
    catch (error: any) { setUpdateError(error.message || "Controllo aggiornamenti non riuscito"); }
    finally { setUpdateBusy(false); }
  }
  async function downloadUpdate() {
    setUpdateBusy(true); setUpdateError("");
    try {
      const response = await fetch("/api/eye/updates/download", { headers: { "X-Eye-Session": currentSession() } });
      if (!response.ok) throw new Error(await response.text());
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a"); link.href = url; link.download = update?.asset_name || "EyeSupremo-Setup.exe"; link.click();
      URL.revokeObjectURL(url);
    } catch (error: any) { setUpdateError(error.message || "Download aggiornamento non riuscito"); }
    finally { setUpdateBusy(false); }
  }
  useEffect(() => {
    if (canManage) api<any[]>("/logs").then(setLogs);
    checkForUpdate();
  }, []);
  const updatePanel = <section className="panel update-panel"><div className="panel-title"><h2>Aggiornamenti</h2><button className="secondary-btn" onClick={checkForUpdate} disabled={updateBusy}><RefreshCw size={15}/> Controlla</button></div>{updateError&&<div className="error">{updateError}</div>}{update?.update_available?<><p>È disponibile Eye Supremo {update.latest_version} (versione installata {update.current_version}).</p><button className="primary-btn" onClick={downloadUpdate} disabled={updateBusy}><Download size={16}/> Scarica installer aggiornato</button></>:<p>{updateBusy?"Controllo la GitHub Release…":update?`Eye Supremo è aggiornato alla versione ${update.current_version}.`:"Controllo versione non ancora eseguito."}</p>}</section>;
  if (!canManage)
    return (<><PageHeader title="Sistema" subtitle="Stato applicazione e aggiornamenti" />{updatePanel}<section className="panel"><Empty title="Accesso riservato" text="I log di sistema sono disponibili solo allo Sviluppatore." /></section></>);
  return (
    <>
      <PageHeader
        title="Sistema"
        subtitle="Stato applicazione e registro attività"
      />
      {updatePanel}
      <section className="panel list-panel">
        {logs?.length ? (
          <div className="log-list">
            {logs.map((l) => (
              <div className="log" key={l.id}>
                <Status tone={l.severity === "error" ? "danger" : "ok"}>
                  {l.event_type}
                </Status>
                <span>{l.message}</span>
                <time>{new Date(l.created_at).toLocaleString("it-IT")}</time>
              </div>
            ))}
          </div>
        ) : (
          <Empty
            title="Nessun evento"
            text="Le operazioni importanti verranno registrate qui."
          />
        )}
      </section>
    </>
  );
}
