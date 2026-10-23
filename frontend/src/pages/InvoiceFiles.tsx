import {useEffect,useState} from 'react';
import {FileDown, Search} from 'lucide-react';
import {apiUrl,currentSession,eyeApi} from '../lib/api';
import {InvoiceViewer,type InvoiceRefTarget} from '../components/InvoiceRef';
import {PageHeader} from '../components/UI';

type Original={id:number;number:string;date:string;supplier:string;filename:string;available:boolean};
export default function InvoiceFiles(){
 const [q,setQ]=useState(''),[submitted,setSubmitted]=useState(''),[items,setItems]=useState<Original[]>([]),[offset,setOffset]=useState(0),[busy,setBusy]=useState(false),[error,setError]=useState(''),[selected,setSelected]=useState<InvoiceRefTarget>();
 useEffect(()=>{let active=true;setBusy(true);setError('');eyeApi<{items:Original[]}>(`/invoice-files?q=${encodeURIComponent(submitted)}&offset=${offset}&limit=100`).then(r=>{if(active)setItems(r.items)}).catch(e=>{if(active)setError(String(e.message||e))}).finally(()=>{if(active)setBusy(false)});return()=>{active=false}},[submitted,offset]);
 async function download(item:Original){
  try{
   const headers:Record<string,string>={'X-Eye-Session':currentSession()};
   const response=await fetch(apiUrl('eye',`/invoice-files/${item.id}/original`),{headers});
   if(!response.ok)throw new Error(response.status===404?'XML non disponibile su questo PC':'Impossibile scaricare il file');
   const blob=await response.blob(),url=URL.createObjectURL(blob),a=document.createElement('a');
   a.href=url;a.download=item.filename||`fattura-${item.id}.xml`;document.body.appendChild(a);a.click();a.remove();URL.revokeObjectURL(url);
  }catch(e:any){setError(e.message||'Errore download')}
 }
 return <><InvoiceViewer target={selected} onClose={()=>setSelected(undefined)}/><PageHeader title="Archivio file fatture" subtitle="Ricerca locale per numero, fornitore, nome XML e prodotto: nessuna IA necessaria" />
 <section className="panel" style={{padding:16}}><form onSubmit={e=>{e.preventDefault();setOffset(0);setSubmitted(q)}} style={{display:'flex',gap:8,flexWrap:'wrap'}}><input aria-label="Cerca fatture" placeholder="Cerca fattura, fornitore o prodotto…" value={q} onChange={e=>setQ(e.target.value)} style={{flex:1,minWidth:220}}/><button className="primary-btn" type="submit"><Search size={16}/> Cerca</button></form>
 {error&&<p role="alert" className="error">{error}</p>}{busy?<p>Ricerca nell'archivio locale…</p>:<><p className="muted">{items.length} fatture nella pagina · {items.filter(x=>x.available).length} XML disponibili sul PC</p><div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Fornitore</th><th>File originale</th><th>Azioni</th></tr></thead><tbody>{items.map(item=><tr key={item.id}><td>{item.date}</td><td>{item.number}</td><td>{item.supplier}</td><td>{item.filename||'Non registrato'} · {item.available?'Sul PC':'Non disponibile'}</td><td><button type="button" className="secondary-btn" onClick={()=>setSelected({id:String(item.id)})}>Apri fattura</button> {item.available&&<button type="button" className="secondary-btn" onClick={()=>download(item)}><FileDown size={14}/> XML</button>}</td></tr>)}</tbody></table></div>
 <div style={{display:'flex',gap:8,marginTop:12}}><button className="secondary-btn" disabled={offset===0} onClick={()=>setOffset(Math.max(0,offset-100))}>Precedenti</button><button className="secondary-btn" disabled={items.length<100} onClick={()=>setOffset(offset+100)}>Successive</button></div></>}</section></>;
}
