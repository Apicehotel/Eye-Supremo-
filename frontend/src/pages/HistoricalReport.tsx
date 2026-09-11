import {useMemo,useState,useEffect} from 'react';
import {ArrowDown,ArrowRight,ArrowUp,Printer,Search,MapPin} from 'lucide-react';
import {eyeApi,euro,shortDate} from '../lib/api';
import {Empty,Loading,PageHeader,SearchBox,Status} from '../components/UI';
import './historical-report.css';

type Point={date:string;price:number;delta:number|null;delta_pct:number|null;trend:'initial'|'up'|'down'|'same';unit:string;invoice:string;description:string};
type SupplierBlock={supplier_id:number;supplier:string;unit:string;manufacturer:string|null;initial_price:number;initial_date:string;average_price:number;best_price:number;best_date:string;latest_price:number;latest_date:string;observations:number;points:Point[]};
type Report={query:string;summary:any;suppliers:SupplierBlock[];dates:string[];units:string[];comparison_note:string};

const PAGE_DATES=8;
const chunks=<T,>(items:T[],size:number)=>Array.from({length:Math.ceil(items.length/size)},(_,i)=>items.slice(i*size,(i+1)*size));

function Trend({point}:{point?:Point}){if(!point)return <span className="hist-empty">—</span>;const Icon=point.trend==='up'?ArrowUp:point.trend==='down'?ArrowDown:ArrowRight;return <div className={`hist-price ${point.trend}`}><b>{euro(point.price)}</b><small><Icon size={12}/>{point.delta===null?'iniziale':`${point.delta>0?'+':''}${point.delta.toFixed(2)} €${point.delta_pct===null?'':` · ${point.delta_pct>0?'+':''}${point.delta_pct.toFixed(1)}%`}`}</small></div>}

export function HistoricalReportPage(){
 const [q,setQ]=useState(''),[submitted,setSubmitted]=useState(''),[data,setData]=useState<Report>(),[busy,setBusy]=useState(false),[error,setError]=useState('');
 async function search(){if(!q.trim())return;setBusy(true);setError('');setSubmitted(q.trim());try{setData(await eyeApi<Report>(`/reports/history-product?q=${encodeURIComponent(q.trim())}`))}catch(e:any){setError(e.message)}finally{setBusy(false)}}
 const comparable=useMemo(()=>data?.summary?data.suppliers.filter(s=>s.unit===data.summary.unit):[],[data]);
 const pages=useMemo(()=>data?.dates?.length?chunks(data.dates,PAGE_DATES):[],[data]);
 return <><div className="screen-only"><PageHeader title="Report storico" subtitle="Prodotto → produttore/marca → fornitore → andamento prezzi"><div className="hist-search"><SearchBox value={q} onChange={setQ} placeholder="Cerca prodotto…"/><button className="primary-btn" onClick={search} disabled={busy}><Search size={16}/>{busy?'Cerco…':'Cerca'}</button>{data?.summary&&<button className="secondary-btn" onClick={()=>window.print()}><Printer size={16}/>Stampa / PDF</button>}</div></PageHeader>{error&&<div className="error">{error}</div>}{busy&&<Loading/>}</div>
 {!busy&&submitted&&data&&!data.summary&&<section className="panel screen-only"><Empty title="Nessuno storico trovato" text={`Nessun acquisto prodotto trovato per “${submitted}”.`}/></section>}
 {data?.summary&&<div className="history-report" id="history-report-print">
   <section className="hist-summary screen-only">
    <article><span>Prezzo iniziale</span><strong>{euro(data.summary.initial_price)}</strong><small>{shortDate(data.summary.initial_date)}</small></article>
    <article><span>Prezzo medio</span><strong>{euro(data.summary.average_price)}</strong><small>per {data.summary.unit}</small></article>
    <article><span>Miglior prezzo</span><strong>{euro(data.summary.best_price)}</strong><small>{shortDate(data.summary.best_date)}</small></article>
    <article><span>Ultimo prezzo</span><strong>{euro(data.summary.latest_price)}</strong><small>{shortDate(data.summary.latest_date)}</small></article>
    <article className="best"><span>Fornitore più conveniente</span><strong>{data.summary.best_supplier}</strong><small>media {euro(data.summary.best_supplier_average)} · {data.summary.best_supplier_observations} rilevazioni</small></article>
   </section>
   <div className="screen-only hist-note"><b>{data.summary.product}</b>{data.summary.manufacturers?.length?<span>Produttore/Marca: {data.summary.manufacturers.join(', ')}</span>:<span>Produttore/Marca da associare</span>}<Status tone="ok">unità confronto: {data.summary.unit}</Status><small>{data.comparison_note}</small></div>
   {pages.map((datePage,pageIndex)=><section className="print-sheet" key={pageIndex}>
    <header className="print-header"><div><b>EYE SUPREMO · REPORT STORICO</b><h1>{data.summary.product}</h1><p>Produttore/Marca: {data.summary.manufacturers?.join(', ')||'da associare'} · Unità: {data.summary.unit}</p></div><div className="print-kpis"><span>Iniziale <b>{euro(data.summary.initial_price)}</b></span><span>Media <b>{euro(data.summary.average_price)}</b></span><span>Migliore <b>{euro(data.summary.best_price)}</b></span><span>Ultimo <b>{euro(data.summary.latest_price)}</b></span><span>Fornitore migliore <b>{data.summary.best_supplier}</b></span></div></header>
    <table className="hist-matrix"><thead><tr><th className="supplier-col">Fornitore</th><th className="maker-col">Produttore / Marca</th>{datePage.map(d=><th key={d}>{shortDate(d)}</th>)}</tr></thead><tbody>{comparable.map(s=><tr key={`${s.supplier_id}-${s.unit}`}><th>{s.supplier}<small>iniz. {euro(s.initial_price)} · media {euro(s.average_price)} · best {euro(s.best_price)} · ultimo {euro(s.latest_price)}</small></th><td>{s.manufacturer||'—'}</td>{datePage.map(d=><td key={d}><Trend point={s.points.find(p=>p.date===d)}/></td>)}</tr>)}</tbody></table>
    <footer>Pagina {pageIndex+1}/{pages.length} · il fornitore e il produttore sono ripetuti su ogni pagina per mantenere il riferimento dei prezzi.</footer>
   </section>)}
  </div>}
 </>;
}

type Destination={id:number;number:string;date:string;supplier:string;total:number;destination:string|null;destination_name:string};
type Hotel={id:number;code:string;name:string};
export function InvoiceDestinationsPage(){const [items,setItems]=useState<Destination[]>(),[hotels,setHotels]=useState<Hotel[]>([]),[q,setQ]=useState('');const load=()=>eyeApi<Destination[]>('/invoice-destinations').then(setItems);useEffect(()=>{Promise.all([load(),eyeApi<Hotel[]>('/hotels').then(setHotels)])},[]);async function change(id:number,hotel_code:string){await eyeApi(`/invoice-destinations/${id}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({hotel_code})});await load()}const visible=items?.filter(x=>(`${x.number} ${x.supplier} ${x.destination_name}`).toLowerCase().includes(q.toLowerCase()));return <><PageHeader title="Destinazione fattura" subtitle="Le fatture sono uniche per Apice; qui indichi solo la destinazione/centro di utilizzo"><SearchBox value={q} onChange={setQ} placeholder="Fattura, fornitore, destinazione…"/></PageHeader><section className="panel list-panel">{!visible?<Loading/>:visible.length?<div className="table-wrap"><table><thead><tr><th>Data</th><th>Fattura</th><th>Fornitore</th><th>Totale</th><th>Destinazione</th></tr></thead><tbody>{visible.map(i=><tr key={i.id}><td>{shortDate(i.date)}</td><td><b>{i.number}</b></td><td>{i.supplier}</td><td>{euro(i.total)}</td><td><label className="destination-select"><MapPin size={14}/><select value={i.destination||'general'} onChange={e=>change(i.id,e.target.value)}><option value="general">Generale / Apice</option>{hotels.map(h=><option key={h.code} value={h.code}>{h.name}</option>)}</select></label></td></tr>)}</tbody></table></div>:<Empty title="Nessuna fattura" text="Le fatture importate compariranno qui per l'assegnazione facoltativa della destinazione."/>}</section></>}
