import {useEffect,useMemo,useState} from 'react';
import {ArrowDown,ArrowUp,Eye,EyeOff,Plus,Printer,Save,Trash2} from 'lucide-react';

type Line={id:string;description:string;qty:number;unit:string;unitPrice:number;tax:number};
type Fields={unit:boolean;tax:boolean;notes:boolean};
type Draft={number:string;date:string;supplier:string;currency:string;status:string;notes:string;fields:Fields;lines:Line[]};

const STORAGE_KEY='eyesupremo.invoice-editor.draft';
const freshLine=():Line=>({id:crypto.randomUUID(),description:'',qty:1,unit:'pz',unitPrice:0,tax:22});
const initialDraft:Draft={number:'',date:new Date().toISOString().slice(0,10),supplier:'',currency:'EUR',status:'Bozza',notes:'',fields:{unit:true,tax:true,notes:true},lines:[freshLine()]};
const money=(value:number,currency:string)=>new Intl.NumberFormat('it-IT',{style:'currency',currency}).format(Number.isFinite(value)?value:0);

export default function InvoiceEditor(){
 const [draft,setDraft]=useState<Draft>(()=>{try{const saved=localStorage.getItem(STORAGE_KEY);return saved?JSON.parse(saved):initialDraft}catch{return initialDraft}});
 const [savedAt,setSavedAt]=useState<string>('');
 useEffect(()=>{localStorage.setItem(STORAGE_KEY,JSON.stringify(draft))},[draft]);
 const subtotal=useMemo(()=>draft.lines.reduce((s,l)=>s+(Number(l.qty)||0)*(Number(l.unitPrice)||0),0),[draft.lines]);
 const taxTotal=useMemo(()=>draft.lines.reduce((s,l)=>s+((Number(l.qty)||0)*(Number(l.unitPrice)||0))*((Number(l.tax)||0)/100),0),[draft.lines]);
 const total=subtotal+taxTotal;
 const patch=(p:Partial<Draft>)=>setDraft(d=>({...d,...p}));
 const linePatch=(id:string,p:Partial<Line>)=>setDraft(d=>({...d,lines:d.lines.map(l=>l.id===id?{...l,...p}:l)}));
 const move=(index:number,delta:number)=>setDraft(d=>{const next=[...d.lines],to=index+delta;if(to<0||to>=next.length)return d;[next[index],next[to]]=[next[to],next[index]];return {...d,lines:next}});
 const save=()=>{localStorage.setItem(STORAGE_KEY,JSON.stringify(draft));setSavedAt(new Date().toLocaleTimeString('it-IT',{hour:'2-digit',minute:'2-digit'}))};
 return <div className="page invoice-editor-page">
  <header className="page-head"><div><p className="eyebrow">Editor locale · ispirato a Manta</p><h1>Editor fattura</h1><p>Correggi rapidamente i dati estratti, riordina le righe e prepara stampa/PDF senza dipendere dal cloud.</p></div><div className="editor-actions"><button className="secondary" onClick={save}><Save size={17}/>Salva bozza</button><button className="primary" onClick={()=>window.print()}><Printer size={17}/>Stampa / PDF</button></div></header>
  {savedAt&&<div className="editor-saved">Bozza salvata alle {savedAt}</div>}
  <section className="editor-grid">
   <div className="editor-panel">
    <h2>Dati documento</h2>
    <div className="editor-form-grid">
     <label>Numero<input value={draft.number} onChange={e=>patch({number:e.target.value})} placeholder="es. FT-2026-001"/></label>
     <label>Data<input type="date" value={draft.date} onChange={e=>patch({date:e.target.value})}/></label>
     <label className="wide">Fornitore<input value={draft.supplier} onChange={e=>patch({supplier:e.target.value})} placeholder="Nome fornitore"/></label>
     <label>Valuta<select value={draft.currency} onChange={e=>patch({currency:e.target.value})}><option>EUR</option><option>USD</option><option>GBP</option></select></label>
     <label>Stato<select value={draft.status} onChange={e=>patch({status:e.target.value})}><option>Bozza</option><option>Da verificare</option><option>Verificata</option><option>Pagata</option></select></label>
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
      {draft.fields.tax&&<label>IVA %<input type="number" min="0" step="1" value={line.tax} onChange={e=>linePatch(line.id,{tax:Number(e.target.value)})}/></label>}
      <div className="line-total"><span>Totale</span><b>{money((Number(line.qty)||0)*(Number(line.unitPrice)||0),draft.currency)}</b></div>
      <button className="danger-icon" disabled={draft.lines.length===1} onClick={()=>patch({lines:draft.lines.filter(l=>l.id!==line.id)})} aria-label="Elimina riga"><Trash2 size={17}/></button>
     </div>)}
    </div>
    {draft.fields.notes&&<label className="editor-notes">Note<textarea rows={4} value={draft.notes} onChange={e=>patch({notes:e.target.value})} placeholder="Note interne o presenti in fattura"/></label>}
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
 </div>
}
