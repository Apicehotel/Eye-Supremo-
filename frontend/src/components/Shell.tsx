import {ReactNode,useState} from 'react';
import {LayoutDashboard,FileText,Package,Users,Upload,Sparkles,ChartNoAxesCombined,History,TriangleAlert,Tags,Settings,MonitorCog,Menu,X,ReceiptText,MessageSquareText,ShieldCheck} from 'lucide-react';

export type Page = 'dashboard'|'invoices'|'products'|'suppliers'|'import'|'ai'|'reports'|'history'|'anomalies'|'categories'|'settings'|'system';
const nav:[Page,string,any][]=[['dashboard','Dashboard',LayoutDashboard],['invoices','Fatture',FileText],['products','Prodotti',Package],['suppliers','Fornitori',Users],['import','Importa',Upload],['ai','Ricerca IA',Sparkles],['reports','Report',ChartNoAxesCombined],['history','Storico',History],['anomalies','Alert',TriangleAlert],['categories','Categorie',Tags],['settings','Impostazioni',Settings],['system','Sistema',MonitorCog]];
const roleOptions=[['developer','Sviluppatore'],['supremo','Supremo'],['level1','Livello 1'],['level2','Livello 2'],['level3','Livello 3']];

export function Shell({page,setPage,area,setArea,children,open,setOpen}:{page:Page,setPage:(p:Page)=>void,area:'invoices'|'reviews',setArea:(a:'invoices'|'reviews')=>void,children:ReactNode,open:boolean,setOpen:(v:boolean)=>void}){
 const [role,setRole]=useState(localStorage.getItem('eye-supremo.role')||'developer');
 const changeRole=(next:string)=>{localStorage.setItem('eye-supremo.role',next);setRole(next);window.location.reload()};
 return <div className="app-shell">
  <aside className={`sidebar ${open?'open':''}`}><div className="brand"><b>EYE</b> SUPREMO<span>Hotel intelligence · Local first</span></div><div className="area-switch" role="group" aria-label="Cambia area"><button className={area==='invoices'?'active':''} onClick={()=>setArea('invoices')}><ReceiptText/>Fatture</button><button className={area==='reviews'?'active':''} onClick={()=>setArea('reviews')}><MessageSquareText/>Recensioni</button></div>{area==='invoices'?<nav>{nav.map(([id,label,Icon])=><button key={id} className={page===id?'active':''} onClick={()=>{setPage(id);setOpen(false)}}><Icon size={19}/><span>{label}</span></button>)}</nav>:<nav><button className="active"><LayoutDashboard size={19}/><span>Panoramica</span></button><button><MessageSquareText size={19}/><span>Recensioni & ranking</span></button><button><Sparkles size={19}/><span>Analisi IA</span></button><button><Settings size={19}/><span>Impostazioni</span></button></nav>}<div className="role-box"><label><ShieldCheck size={15}/>Profilo</label><select value={role} onChange={e=>changeRole(e.target.value)}>{roleOptions.map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></div><div className="local-status"><i/>Archivio locale<small>Windows · Offline first · Sync opzionale</small></div></aside>
  {open&&<button className="scrim" aria-label="Chiudi menu" onClick={()=>setOpen(false)}/>}<main><button className="mobile-menu" onClick={()=>setOpen(!open)}>{open?<X/>:<Menu/>}</button>{children}</main>
 </div>
}
