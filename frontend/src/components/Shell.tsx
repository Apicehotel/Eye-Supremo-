import {ReactNode} from 'react';
import {LayoutDashboard,FileText,Package,Users,Upload,Sparkles,ChartNoAxesCombined,History,TriangleAlert,Tags,Settings,MonitorCog,Menu,X,ReceiptText,MessageSquareText,ShieldCheck,LogOut} from 'lucide-react';
import {clearAuth,currentUser,eyeApi} from '../lib/api';

export type Page = 'dashboard'|'invoices'|'products'|'suppliers'|'import'|'ai'|'reports'|'history'|'anomalies'|'categories'|'settings'|'system';
const nav:[Page,string,any][]=[['dashboard','Dashboard',LayoutDashboard],['invoices','Fatture',FileText],['products','Prodotti',Package],['suppliers','Fornitori',Users],['import','Importa',Upload],['ai','Ricerca IA',Sparkles],['reports','Report',ChartNoAxesCombined],['history','Storico',History],['anomalies','Alert',TriangleAlert],['categories','Categorie',Tags],['settings','Impostazioni',Settings],['system','Sistema',MonitorCog]];

export function Shell({page,setPage,area,setArea,children,open,setOpen}:{page:Page,setPage:(p:Page)=>void,area:'invoices'|'reviews',setArea:(a:'invoices'|'reviews')=>void,children:ReactNode,open:boolean,setOpen:(v:boolean)=>void}){
 const user=currentUser(); const isDeveloper=user?.role_name==='developer';
 const visibleNav=nav.filter(([id])=>isDeveloper||!['settings','system'].includes(id));
 async function logout(){try{await eyeApi('/auth/logout',{method:'POST'})}catch{}clearAuth();window.dispatchEvent(new Event('eye-auth-expired'))}
 return <div className="app-shell">
  <aside className={`sidebar ${open?'open':''}`}><div className="brand"><b>EYE</b> SUPREMO<span>Hotel intelligence · Local first</span></div><div className="area-switch" role="group" aria-label="Cambia area"><button className={area==='invoices'?'active':''} onClick={()=>setArea('invoices')}><ReceiptText/>Fatture</button><button className={area==='reviews'?'active':''} onClick={()=>setArea('reviews')}><MessageSquareText/>Recensioni</button></div>{area==='invoices'?<nav>{visibleNav.map(([id,label,Icon])=><button key={id} className={page===id?'active':''} onClick={()=>{setPage(id);setOpen(false)}}><Icon size={19}/><span>{label}</span></button>)}</nav>:<nav><button className="active"><LayoutDashboard size={19}/><span>Panoramica</span></button><button><MessageSquareText size={19}/><span>Recensioni & ranking</span></button><button><Sparkles size={19}/><span>Analisi IA</span></button>{isDeveloper&&<button><Settings size={19}/><span>Impostazioni</span></button>}</nav>}<div className="role-box"><label><ShieldCheck size={15}/>{user?.display_name||'Utente'}</label><small>{user?.role_name||'profilo locale'}</small><button onClick={logout}><LogOut size={15}/>Esci</button></div><div className="local-status"><i/>Archivio locale<small>Windows · Offline first · Sync opzionale</small></div></aside>
  {open&&<button className="scrim" aria-label="Chiudi menu" onClick={()=>setOpen(false)}/>}<main><button className="mobile-menu" onClick={()=>setOpen(!open)}>{open?<X/>:<Menu/>}</button>{children}</main>
 </div>
}
