import {useEffect,useMemo,useState} from 'react';
import {ArrowDown,ArrowUp,Eye,EyeOff,Plus,Printer,RefreshCw,Save,Trash2} from 'lucide-react';
import {api} from '../lib/api';

type Line={id:string;description:string;qty:number;unit:string;unitPrice:number;tax:number};
type Fields={unit:boolean;tax:boolean;notes:boolean};
type Draft={invoiceId:number|null;number:string;date:string;supplier:string;currency:string;status:string;notes:string;fields:Fields;lines:Line[]};
type InvoiceDetail={id:number;numero:string;data:string;valuta:string;stato_importazione:string;testo_estratto?:string|null;supplier:{id:number;ragione_sociale:string};rows:Array<{id:number;descrizione_originale:string;descrizione_normalizzata?:string|null;product?:string|null;quantita:number;unita_originale?:string|null;unita_normalizzata?:string|null;prezzo_unitario:number;aliquota_iva?:number|null}>};

const STORAGE_KEY='eyesupremo.invoice-editor.draft';
const storageKey=(invoiceId:number|null)=>invoiceId?`${STORAGE_KEY}.${invoiceId}`:STORAGE_KEY;
const freshLine=():Line=>({id:crypto.randomUUID(),description:'',qty:1,unit:'pz',unitPrice:0,tax:22});
const freshDraft=():Draft=>({invoiceId:null,number:'',date:new Date().toISOString().slice(0,10),supplier:'',currency:'EUR',status:'Bozza',notes:'',fields:{unit:true,tax:true,notes:true},lines:[freshLine()]});
const money=(value:number,currency:string)=>{try{return new Intl.NumberFormat('it-IT',{style:'currency',currency:currency||'EUR'}).format(Number.isFinite(value)?value:0)}catch{return `${(Number.isFinite(value)?value:0).toFixed(2)} ${currency||'EUR'}`}};
const fromInvoice=(inv:InvoiceDetail):Draft=>({invoiceId:inv.id,number:inv.numero,date:inv.data.slice(0,10),supplier:inv.supplier?.ragione_sociale||'',currency:inv.valuta||'EUR',status:inv.stato_importazione||'Verificata',notes:'',fields:{unit:true,tax:true,notes:true},lines:inv.rows.length?inv.rows.map(r=>({id:`row-${r.id}`,description:r.descrizione_normalizzata||r.product||r.descrizione_originale||'',qty:Number(r.quantita)||0,unit:r.unita_normalizzata||r.unita_originale||'pz',unitPrice:Number(r.prezzo_unitario)||0,tax:Number(r.aliquota_iva)||0})):[freshLine()]});

export default function InvoiceEditor({invoiceId=null}:{invoiceId?:number|null}){
 const [draft,setDraft]=useState<Draft>(()=>{if(invoiceId)return freshDraft();try{const saved=localStorage.getItem(STORAGE_KEY);return saved?JSON.parse(saved):freshDraft()}catch{return freshDraft()}});
 const [savedAt,setSavedAt]=useState<string>('');
 const [loading,setLoading]=useState(Boolean(invoiceId));
 const [error,setError]=useState('');

 const loadInvoice=()=>{
  if(!invoiceId)return;
  setLoading(true);setError('');
  api<InvoiceDetail>(`/invoices/${invoiceId}`).then(inv=>{const serverDraft=fromInvoice(inv);try{const cached=localStorage.getItem(storageKey(invoiceId));setDraft(cached?{...serverDraft,...JSON.parse(cached),invoiceId}:serverDraft)}catch{setDraft(serverDraft)}}).catch(()=>setError('Impossibile caricare la fattura. Verifica che il backend sia attivo e che il documento esista.')).finally(()=>setLoading(false));
 };
 useEffect(()=>{if(invoiceId)loadInvoice();else{try{const saved=localStorage.getItem(STORAGE_KEY);setDraft(saved?JSON.parse(saved):freshDraft())}catch{setDraft(freshDraft())}setLoading(false);setError('')}},[invoiceId]);
 useEffect(()=>{if(!loading)localStorage.setItem(storageKey(invoiceId),JSON.stringify({...draft,invoiceId}))},[draft,invoiceId,loading]);

 const subtotal=useMemo(()=>draft.lines.reduce((s,l)=>s+(Number(l.qty)||0)*(Number(l.unitPrice)||0),0),[draft.lines]);
 const taxTotal=useMemo(()=>draft.lines.reduce((s,l)=>s+((Number(l.qty)||0)*(Number(l.unitPrice)||0))*((Number(l.tax)||0)/100),0),[draft.lines]);
 const total=subtotal+taxTotal;
 const patch=(p:Partial<Draft>)=>setDraft(d=>({...d,...p}));
 const linePatch=(id:string,p:Partial<Line>)=>setDraft(d=>({...d,lines:d.lines.map(l=>l.id===id?{...l,...p}:l)}));
 const move=(index:number,delta:number)=>setDraft(d=>{const next=[...d.lines],to=index+delta;if(to<0||to>=next.length)return d;[next[index],next[to]]=[next[to],next[index]];return {...d,lines:next}});
 const save=()=>{localStorage.setItem(storageKey(invoiceId),JSON.stringify({...draft,invoiceId}));setSavedAt(new Date().toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit'}))};
 const resetFromArchive=()=>{if(invoiceId){localStorage.removeItem(storageKey(invoiceId));loadInvoice()}else{localStorage.removeItem(STORAGE_KEY);setDraft(freshDraft());setSavedAt('')}};

 if(loading)return <div className="page invoice-editor-page"><header className="page-head"><div><p className="eyebrow">Editor fattura</p><h1>Caricamento documento…</h1><p>Sto recuperando i dati importati e le righe normalizzate.</p></div></header></div>;
 return <div className="page invoice-editor-page">
  <header className="page-head"><div><p className="eyebrow">{invoiceId?'Fattura importata · correzioni locali':'Editor locale · nuova bozza'}</p><h1>Editor fattura</h1><p>{invoiceId?'Dati caricati dall’archivio Eye Supremo. Le modifiche restano in bozza locale finché non viene aggiunta la conferma definitiva.':'Crea o prepara una fattura manualmente, anche offline.'}</p></div><div className="editor-actions"><button className="secondary" onClick={resetFromArchive}><RefreshCw size={17}/>{invoiceId?'Ricarica originale':'Nuova bozza'}</button><button className="secondary" onClick={save}><Save size={17}/>Salva bozza</button><button className="primary" onClick={()=>window.print()}><Printer size={17}/>Stampa / PDF</button></div></header>
  {error&&<div className="editor-saved" style={{background:'#fef3f2',color:'#b42318'}}>{error}</div>}
  {savedAt&&<div className="editor-saved">Bozza salvata alle {savedAt}</div>}
  <section className="editor-grid">
   <div className="editor-panel">
    <h2>Dati documento</h2>
    <div className="editor-form-grid">
     <label>Numero<input value={draft.number} onChange={e=>patch({number:e.target.value})} placeholder="es. FT-2026-001"/></label>
     <label>Data<input type="date" value={draft.date} onChange={e=>patch({date:e.target.value})}/></label>
     <label className="wide">Fornitore<input value={draft.supplier} onChange={e=>patch({supplier:e.target.value})} placeholder="Nome fornitore"/></label>
     <label>Valuta<select value={draft.currency} onChange={e=>patch({currency:e.target.value})}><option>EUR</option><option>USD</option><option>GBP</option></select></label>
     <label>Stato<select value={draft.status} onChange={e=>patch({status:e.target.value})}><option>Bozza</option><option>Da verificare</option><option>Verificata</option><option>Pagata</option><option>confermata</option></select></label>
    </div>
    <div className="editor-field-toggle"><b>Campi visibili</b><button onClick={()=>patch({fields:{...draft.fields,unit:!draft.fields.unit}})}>{draft.fields.unit?<Eye size={16}/>:<EyeOff size={16}/>}Unità</button><button onClick={()=>patch({fields:{...draft.fields,tax:!draft.fields.tax}})}>{draft.fields.tax?<Eye size={16}/>:<EyeOff size={16}/>}IVA</button><button onClick={()=>patch({fields:{...draft.fields,notes:!draft.fields.notes}})}>{draft.fields.notes?<Eye size={16}/>:<EyeOff size={16}/>}Note</button></div>
    <div className="editor-lines-head"><h2>Righe fattura</h2><button className="secondary" onClick={()=>patch({lines:[...draft.lines,freshLine()]})}><Plus size={17}/>Aggiungi riga</button></div>
    <div className="editor-lines">
     {draft.lines.map((line,index)=><div className="editor-line" key={line.id}>
      <div className="line-order"><button disabled={index===0} onClick={()=>move(index,-1)} aria-label="Sposta su"><ArrowUp size={16}/></button><button disabled={index===draft.lines.length-1} onClick={()=>move(index,1)} aria-label="Sposta giù"><ArrowDown size={16}/></button></div>
      <label className="line-description">Descrizione<input value={line.description} onChange={e=>linePatch(line.id,{description:e.target.value})} placeholder="Prodotto o servizio"/></label>
      <label>Qtà<input type="number" min="0" step="0.01" value={line.qty} onChange={e=>linePatch(line.id,{qty:Number(e.target.value)})}/></label>
      {draft.fields.unit&&<label>Unità<input value={line.unit} onChange={e=>linePatch(line.id,{unit:e.target.value})}/></label>}
      <label>Prezzo<input type="number" min="0" step="0.01" value={line.unitPrice} onChange={e=>linePatch(line.id,{unitPrice:Number(e.target.value)})}/></label>
      {draft.fields.tax&&<label>IVA %<input type="number" min="0" step="0.01" value={line.tax} onChange={e=>linePatch(line.id,{tax:Number(e.target.value)})}/></label>}
      <div className="line-total"><span>Totale</span><b>{money((Number(line.qty)||0)*(Number(line.unitPrice)||0),draft.currency)}</b></div>
      <button className="danger-icon" disabled={draft.lines.length===1} onClick={()=>patch({lines:draft.lines.filter(l=>l.id!==line.id)})} aria-label="Elimina riga"><Trash2 size={17}/></button>
     </div>)}
    </div>
    {draft.fields.notes&&<label className="editor-notes">Note<textarea rows={4} value={draft.notes} onChange={e=>patch({notes:e.target.value})} placeholder="Note locali o di verifica"/></label>}
   </div>
   <aside className="invoice-preview">
    <div className="preview-paper">
     <div className="preview-brand"><b>EYE SUPREMO</b><span>{draft.status}</span></div><h2>FATTURA {draft.number||'—'}</h2><p><b>Fornitore:</b> {draft.supplier||'—'}</p><p><b>Data:</b> {draft.date||'—'}</p>
     <table><thead><tr><th>Descrizione</th><th>Qtà</th>{draft.fields.unit&&<th>U.M.</th>}<th>Prezzo</th>{draft.fields.tax&&<th>IVA</th>}<th>Totale</th></tr></thead><tbody>{draft.lines.map(l=><tr key={l.id}><td>{l.description||'—'}</td><td>{l.qty}</td>{draft.fields.unit&&<td>{l.unit}</td>}<td>{money(l.unitPrice,draft.currency)}</td>{draft.fields.tax&&<td>{l.tax}%</td>}<td>{money(l.qty*l.unitPrice,draft.currency)}</td></tr>)}</tbody></table>
     <div className="preview-totals"><span>Imponibile <b>{money(subtotal,draft.currency)}</b></span>{draft.fields.tax&&<span>IVA <b>{money(taxTotal,draft.currency)}</b></span>}<span className="grand-total">Totale <b>{money(total,draft.currency)}</b></span></div>
     {draft.fields.notes&&draft.notes&&<div className="preview-notes"><b>Note</b><p>{draft.notes}</p></div>}
    </div>
   </aside>
  </section>
 </div>;
}
