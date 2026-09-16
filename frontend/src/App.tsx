import {useState} from 'react';
import {Shell,Page} from './components/Shell';
import Dashboard from './pages/Dashboard';
import {HistoryPage,Invoices,Products,Reports,SimplePage,Suppliers} from './pages/Lists';
import {AIPage,ImportPage,SettingsPage,SystemPage} from './pages/ImportAISettings';
import Reviews from './pages/Reviews';
import InvoiceEditor from './pages/InvoiceEditor';
import './pages/InvoiceEditor.css';

export default function App(){
 const [page,setPage]=useState<Page>('dashboard');
 const [editingInvoiceId,setEditingInvoiceId]=useState<number|null>(null);
 const [area,setAreaState]=useState<'invoices'|'reviews'>(()=>localStorage.getItem('randfatture.area')==='reviews'?'reviews':'invoices');
 const [open,setOpen]=useState(false);
 const setArea=(next:'invoices'|'reviews')=>{localStorage.setItem('randfatture.area',next);setAreaState(next)};
 const navigate=(next:Page)=>{if(next==='editor')setEditingInvoiceId(null);setPage(next)};
 const openInvoice=(id:number)=>{setEditingInvoiceId(id);setPage('editor')};
 let content;
 if(area==='reviews') content=<Reviews/>;
 else switch(page){
  case'dashboard':content=<Dashboard go={navigate}/>;break;
  case'invoices':content=<Invoices onOpen={openInvoice}/>;break;
  case'editor':content=<InvoiceEditor invoiceId={editingInvoiceId}/>;break;
  case'products':content=<Products/>;break;
  case'suppliers':content=<Suppliers/>;break;
  case'import':content=<ImportPage/>;break;
  case'ai':content=<AIPage/>;break;
  case'reports':content=<Reports/>;break;
  case'history':content=<HistoryPage/>;break;
  case'settings':content=<SettingsPage/>;break;
  case'system':content=<SystemPage/>;break;
  case'anomalies':content=<SimplePage title="Anomalie" subtitle="Controlli automatici su prezzi, quantità e coerenza"/>;break;
  default:content=<SimplePage title="Categorie" subtitle="Classificazione dei prodotti e della spesa"/>;
 }
 return <Shell page={page} setPage={navigate} area={area} setArea={setArea} open={open} setOpen={setOpen}>{content}</Shell>;
}
