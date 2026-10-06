import { ChangeEvent, useState } from "react";
import { Download, ImagePlus, Send } from "lucide-react";
import { PageHeader } from "../components/UI";

type FeedbackDraft = { problem: string; area: string; screenshot?: string; filename?: string; createdAt: string };

export default function FeedbackPage() {
  const [problem, setProblem] = useState("");
  const [area, setArea] = useState("Generale");
  const [screenshot, setScreenshot] = useState<string>();
  const [filename, setFilename] = useState("");
  const [saved, setSaved] = useState(false);

  function onFile(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    if (!file || !file.type.startsWith("image/")) return;
    if (file.size > 5 * 1024 * 1024) { window.alert("Lo screenshot deve essere massimo 5 MB."); return; }
    setFilename(file.name);
    const reader = new FileReader();
    reader.onload = () => setScreenshot(String(reader.result));
    reader.readAsDataURL(file);
  }

  function draft(): FeedbackDraft { return { problem: problem.trim(), area, screenshot, filename, createdAt: new Date().toISOString() }; }
  function save() { if (!problem.trim()) return; localStorage.setItem("eye-supremo.feedback.last", JSON.stringify(draft())); setSaved(true); }
  function download() {
    if (!problem.trim()) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(draft(), null, 2)], { type: "application/json" }));
    const link = document.createElement("a"); link.href = url; link.download = `eye-supremo-feedback-${new Date().toISOString().slice(0, 10)}.json`; link.click(); URL.revokeObjectURL(url);
  }

  return <>
    <PageHeader title="Feedback" subtitle="Segnala un problema con descrizione e screenshot" />
    <section className="panel feedback-panel">
      <div className="feedback-intro"><div><h2>Invia una segnalazione</h2><p>Scrivi cosa non funziona e allega lo screenshot della schermata. Il pacchetto può essere salvato e inviato allo sviluppatore.</p></div><Send /></div>
      <div className="feedback-grid">
        <label>Sezione interessata<select value={area} onChange={e => setArea(e.target.value)}><option>Generale</option><option>Dashboard</option><option>Fatture</option><option>Prodotti</option><option>Fornitori</option><option>Recensioni</option><option>Ricerca IA</option><option>Report storico</option></select></label>
        <label className="feedback-file"><span>Screenshot</span><input type="file" accept="image/png,image/jpeg,image/webp" onChange={onFile} /><span className="feedback-file-button"><ImagePlus size={17} /> {filename || "Scegli immagine"}</span></label>
      </div>
      <label className="feedback-problem">Descrivi il problema<textarea value={problem} onChange={e => { setProblem(e.target.value); setSaved(false); }} placeholder="Esempio: cliccando su Fatture non si apre il dettaglio..." /></label>
      {screenshot && <div className="feedback-preview"><img src={screenshot} alt="Anteprima screenshot" /><button className="secondary-btn" onClick={() => { setScreenshot(undefined); setFilename(""); }}>Rimuovi screenshot</button></div>}
      <div className="feedback-actions"><button className="secondary-btn" onClick={download} disabled={!problem.trim()}><Download size={16} /> Scarica segnalazione</button><button className="primary-btn" onClick={save} disabled={!problem.trim()}><Send size={16} /> Salva feedback</button></div>
      {saved && <div className="success">Feedback salvato localmente. Scarica la segnalazione per inviarla allo sviluppatore.</div>}
    </section>
  </>;
}
