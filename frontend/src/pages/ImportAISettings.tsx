import {useEffect,useRef,useState} from 'react';
import {UploadCloud,FileCheck,BrainCircuit,DatabaseBackup,RefreshCw} from 'lucide-react';
import {api,currentRole,currentSession,currentUser,eyeApi,euro} from '../lib/api';
import {Empty,PageHeader,Status} from '../components/UI';
import {UserAdmin} from '../components/UserAdmin';

type Hotel={id:number;code:string;name:string};
type BatchItem={filename:string;ok:boolean;error?:string;preview?:any;confirmed?:boolean;confirmError?:string;result?:any};

export function ImportPage(){
  const input=useRef<HTMLInputElement>(null),[busy,setBusy]=useState(false),[items,setItems]=useState<BatchItem[]>([]),[selectedJob,setSelectedJob]=useState<number|undefined>(),[error,setError]=useState(''),[done,setDone]=useState('');
  const preview=items.find(x=>x.ok&&x.preview?.job_id===selectedJob)?.preview;
  const ready=items.filter(x=>x.ok&&!x.confirmed).length;
  const confirmed=items.filter(x=>x.confirmed).length;
  const failed=items.filter(x=>!x.ok||x.confirmError).length;

  async function upload(files:File[]){
    if(!files.length)return;
    setBusy(true);setError('');setDone('');setItems([]);setSelectedJob(undefined);
    const body=new FormData();files.forEach(file=>body.append('files',file));
    try{
      const headers:Record<string,string>={'X-Eye-Role':currentRole()};if(currentSession())headers['X-Eye-Session']=currentSession();
      const res=await fetch('/api/eye/invoices/import/preview-batch',{method:'POST',headers,body});
      if(!res.ok)throw new Error(await res.text());
      const result=await res.json();
      const batch:BatchItem[]=result.items||[];setItems(batch);
      const first=batch.find(x=>x.ok&&x.preview);if(first)setSelectedJob(first.preview.job_id);
      setDone(`${result.ready} fatture pronte${result.failed?` · ${result.failed} file scartati`:''}`);
    }catch(e:any){setError(e.message)}finally{setBusy(false);if(input.current)input.current.value=''}
  }

  async function confirmOne(index:number){
    const item=items[index];if(!item?.ok||!item.preview||item.confirmed)return;
    try{
      const result:any=await eyeApi(`/invoices/import/${item.preview.job_id}/confirm`,{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'});
      setItems(current=>current.map((x,i)=>i===index?{...x,confirmed:true,confirmError:undefined,result}:x));
      return true;
    }catch(e:any){setItems(current=>current.map((x,i)=>i===index?{...x,confirmError:e.message}:x));return false}
  }

  async function confirmAll(){
    setBusy(true);setError('');let ok=0,bad=0;
    for(let i=0;i<items.length;i++){if(items[i].ok&&!items[i].confirmed){(await confirmOne(i))?ok++:bad++}}
    setDone(`${ok} fatture salvate${bad?` · ${bad} da verificare`:''}`);setBusy(false);
  }

  return <><PageHeader title="Importa fatture" subtitle="Archivio unico Apice · multi-file e ZIP · massimo 100 fatture per lotto"/>
    <section className="import-layout">
      <article className="panel dropzone" onClick={()=>input.current?.click()} onDragOver={e=>e.preventDefault()} onDrop={e=>{e.preventDefault();upload(Array.from(e.dataTransfer.files))}}>
        <UploadCloud/><h2>{busy?'Operazione in corso…':'Trascina qui fatture o uno ZIP'}</h2>
        <p>Puoi selezionare più XML/TXT/PDF insieme oppure uno ZIP. Eye Supremo estrae e analizza fino a 100 fatture per lotto.</p>
        <p>XML FatturaPA, TXT, PDF, ZIP · massimo 30 MB per fattura</p>
        <button className="primary-btn">Seleziona file</button>
        <input ref={input} hidden multiple type="file" accept=".xml,.txt,.pdf,.zip" onChange={e=>upload(Array.from(e.target.files||[]))}/>
        {error&&<div className="error">{error}</div>}{done&&<div className="success">{done}</div>}
      </article>

      {items.length>0?<article className="panel preview">
        <div className="panel-title"><h2>Lotto importazione</h2><Status tone={failed?'warn':'ok'}>{confirmed}/{items.length} salvate</Status></div>
        <div className="form-actions"><button className="primary-btn" disabled={busy||ready===0} onClick={confirmAll}><FileCheck/>Conferma tutte ({ready})</button></div>
        <div className="table-wrap"><table><thead><tr><th>File</th><th>Stato</th><th>Fornitore</th><th>Totale</th></tr></thead><tbody>{items.map((item,i)=><tr key={`${item.filename}-${i}`} className={item.preview?.job_id===selectedJob?'active-row':''} onClick={()=>item.preview&&setSelectedJob(item.preview.job_id)}><td>{item.filename}</td><td>{item.confirmed?<Status tone="ok">Salvata</Status>:item.confirmError?<Status tone="danger">Da verificare</Status>:item.ok?<Status tone="ok">Pronta</Status>:<Status tone="danger">Scartata</Status>}</td><td>{item.preview?.supplier?.ragione_sociale||item.error||item.confirmError||'—'}</td><td>{item.preview?.invoice?.totale!=null?euro(Number(item.preview.invoice.totale)):'—'}</td></tr>)}</tbody></table></div>
      </article>:<article className="panel preview"><Empty title="Import multiplo" text="Seleziona fino a 100 fatture oppure uno ZIP. I file non supportati vengono scartati senza bloccare il resto del lotto."/></article>}
    </section>

    {preview&&<section className="panel preview" style={{marginTop:16}}><div className="panel-title"><h2>Anteprima · {preview.filename}</h2><Status tone={preview.confidence>.8?'ok':'warn'}>{Math.round(preview.confidence*100)}% confidenza</Status></div><div className="preview-grid"><label>Fornitore<input readOnly value={preview.supplier.ragione_sociale||''}/></label><label>Numero<input readOnly value={preview.invoice.numero||''}/></label><label>Data<input readOnly type="date" value={preview.invoice.data||''}/></label><label>Totale<input readOnly value={preview.invoice.totale??''}/></label></div>{preview.duplicate_matches?.length>0&&<div className="warning">Possibile duplicato: #{preview.duplicate_matches.join(', #')}</div>}<h3>{preview.rows.length} righe rilevate</h3><div className="table-wrap"><table><thead><tr><th>Descrizione</th><th>Quantità</th><th>Unità</th><th>Prezzo</th><th>Confidenza</th></tr></thead><tbody>{preview.rows.map((r:any,i:number)=><tr key={i}><td>{r.descrizione_originale}</td><td>{r.quantita}</td><td>{r.unita_originale||'—'}</td><td>{euro(Number(r.prezzo_unitario))}</td><td>{Math.round(r.confidence*100)}%</td></tr>)}</tbody></table></div></section>}
  </>;
}

export function AIPage(){const [q,setQ]=useState(''),[answer,setAnswer]=useState<any>(),[busy,setBusy]=useState(false),[hotel,setHotel]=useState(''),[hotels,setHotels]=useState<Hotel[]>([]);useEffect(()=>{eyeApi<Hotel[]>('/hotels').then(setHotels)},[]);async function ask(){if(!q.trim())return;setBusy(true);try{setAnswer(await eyeApi('/agents/ask',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({question:q,hotel_code:hotel||undefined})}))}finally{setBusy(false)}}return <><PageHeader title="Eye AI" subtitle="Orchestratore Qwen: prodotti, prezzi, fatture, recensioni e verifica"><select value={hotel} onChange={e=>setHotel(e.target.value)}><option value="">Tutti gli hotel</option>{hotels.map(h=><option key={h.code} value={h.code}>{h.name}</option>)}</select></PageHeader><section className="ai-layout"><article className="panel ai-hero"><BrainCircuit/><h2>Cosa vuoi sapere?</h2><div className="ask-box"><textarea value={q} onChange={e=>setQ(e.target.value)} placeholder="Es. Chi mi vende meglio i bomboloni? Quali sono le 5 camere peggiori?"/><button className="primary-btn" onClick={ask}>{busy?'Agenti al lavoro…':'Chiedi'}</button></div><div className="examples">{['Chi mi vende meglio i bomboloni?','Top 5 camere migliori','Quanto è aumentata l’acqua naturale?','Classifica questo prodotto'].map(x=><button onClick={()=>setQ(x)} key={x}>{x}</button>)}</div></article>{answer&&<article className="panel ai-answer"><div className="panel-title"><h2>Risposta</h2><Status tone={answer.mode==='orchestrated-ollama'?'ok':'warn'}>{answer.mode==='orchestrated-ollama'?'Qwen + agenti':'Agenti locali'}</Status></div><p>{answer.answer}</p>{answer.agents?.length>0&&<small>Agenti: {answer.agents.map((a:any)=>a.name).join(' → ')}</small>}{answer.verification?.warnings?.map((w:string)=><div className="warning" key={w}>{w}</div>)}{answer.context?.invoice_summary&&<small>Righe pertinenti: {answer.context.invoice_summary.rows} · Totale righe: {euro(answer.context.invoice_summary.row_total)}</small>}</article>}</section></>}

export function SettingsPage(){const user=currentUser();const [data,setData]=useState<any>(),[status,setStatus]=useState<any>(),[sync,setSync]=useState<any>();useEffect(()=>{if(user?.role_name==='developer'){api('/settings').then(setData);api('/ollama/status').then(setStatus);eyeApi('/sync/status').then(setSync)}},[]);if(user?.role_name!=='developer')return <><PageHeader title="Impostazioni" subtitle="Area riservata allo Sviluppatore"/><section className="panel"><Empty title="Accesso riservato" text="Il profilo corrente non può modificare configurazione, utenti o backup."/></section></>;async function save(){await api('/settings',{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});alert('Impostazioni salvate')}async function backup(){const r:any=await api('/backups',{method:'POST'});alert(`Backup creato: ${r.filename}`)}return <><PageHeader title="Impostazioni" subtitle="Utenti, IA locale, sincronizzazione, backup e sicurezza"/><UserAdmin/><div className="settings-layout"><aside className="settings-nav">{['Generali','Hotel','Utenti e ruoli','Esclusioni fatture','IA locale','Sincronizzazione','Backup','Sicurezza'].map((x,i)=><button className={i===4?'active':''} key={x}>{x}</button>)}</aside><section className="panel settings-form"><div className="panel-title"><h2>Qwen / Ollama</h2><Status tone={status?.available?'ok':'warn'}>{status?.available?'Connesso':'Non disponibile'}</Status></div>{data&&<><label>URL Ollama<input value={data.ollama_url} onChange={e=>setData({...data,ollama_url:e.target.value})}/></label><label>Modello chat<input value={data.chat_model} onChange={e=>setData({...data,chat_model:e.target.value})}/></label><label>Modello embedding<input value={data.embedding_model} onChange={e=>setData({...data,embedding_model:e.target.value})}/></label><div className="form-actions"><button className="secondary-btn" onClick={()=>api('/ollama/status').then(setStatus)}><RefreshCw/>Test IA</button><button className="primary-btn" onClick={save}>Salva</button></div><hr/><h2>Ponte Supabase</h2><p>{sync?.enabled?'Sincronizzazione attiva':'Local-first: sincronizzazione disattivata finché non viene configurata.'}</p><hr/><h2>Backup locale</h2><button className="secondary-btn" onClick={backup}><DatabaseBackup/>Crea backup ora</button></>}</section></div></>}

export function SystemPage(){const user=currentUser();const [logs,setLogs]=useState<any[]>();useEffect(()=>{if(user?.role_name==='developer')api<any[]>('/logs').then(setLogs)},[]);if(user?.role_name!=='developer')return <><PageHeader title="Sistema" subtitle="Area riservata allo Sviluppatore"/><section className="panel"><Empty title="Accesso riservato" text="I log di sistema sono disponibili solo allo Sviluppatore."/></section></>;return <><PageHeader title="Sistema" subtitle="Stato applicazione e registro attività"/><section className="panel list-panel">{logs?.length?<div className="log-list">{logs.map(l=><div className="log" key={l.id}><Status tone={l.severity==='error'?'danger':'ok'}>{l.event_type}</Status><span>{l.message}</span><time>{new Date(l.created_at).toLocaleString('it-IT')}</time></div>)}</div>:<Empty title="Nessun evento" text="Le operazioni importanti verranno registrate qui."/>}</section></>}
