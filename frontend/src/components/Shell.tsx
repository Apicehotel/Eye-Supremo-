import {ReactNode} from 'react';
import {
  LayoutDashboard, FileText, FilePenLine, Package, Boxes, Users, Upload, Sparkles,
  ChartNoAxesCombined, History, TriangleAlert, Tags, Settings, MonitorCog, Menu, X,
  ReceiptText, MessageSquareText, CloudUpload, Inbox, LogOut,
} from 'lucide-react';
import {clearAuth, AuthUser} from '../lib/api';

export type Page =
  | 'dashboard' | 'invoices' | 'editor' | 'products' | 'warehouse' | 'suppliers'
  | 'import' | 'storage-inbox' | 'central-catalog' | 'ai' | 'reports' | 'history' | 'anomalies'
  | 'categories' | 'settings' | 'system' | 'uploader';

const nav: [Page, string, any][] = [
  ['dashboard', 'Dashboard', LayoutDashboard],
  ['invoices', 'Fatture', FileText],
  ['editor', 'Editor fattura', FilePenLine],
  ['products', 'Prodotti', Package],
  ['warehouse', 'Magazzino', Boxes],
  ['suppliers', 'Fornitori', Users],
  ['import', 'Importa', Upload],
  ['storage-inbox', 'Coda Storage', Inbox],
  ['ai', 'Ricerca IA', Sparkles],
  ['reports', 'Report', ChartNoAxesCombined],
  ['history', 'Storico', History],
  ['anomalies', 'Anomalie', TriangleAlert],
  ['categories', 'Categorie', Tags],
  ['settings', 'Impostazioni', Settings],
  ['system', 'Sistema', MonitorCog],
];

export function Shell({
  page, setPage, area, setArea, children, open, setOpen, user,
}: {
  page: Page;
  setPage: (p: Page) => void;
  area: 'invoices' | 'reviews';
  setArea: (a: 'invoices' | 'reviews') => void;
  children: ReactNode;
  open: boolean;
  setOpen: (v: boolean) => void;
  user: AuthUser | null;
}) {
  const uploaderOnly = user?.role_name === 'uploader';
  function logout() {
    const session = localStorage.getItem('randfatture.session');
    fetch('/api/auth/logout', {method: 'POST', headers: {'X-Eye-Session': session || ''}}).finally(() => {
      clearAuth();
      window.dispatchEvent(new Event('eye-auth-expired'));
    });
  }

  return (
    <div className="app-shell">
      <aside className={`sidebar ${open ? 'open' : ''}`}>
        <div className="brand">
          <b>RAND</b>FATTURE
          <span>{uploaderOnly ? 'Solo carico file' : area === 'invoices' ? 'Le tue fatture, più valore.' : 'Ascolta, rispondi, migliora.'}</span>
        </div>
        {!uploaderOnly && (
          <div className="area-switch" role="group" aria-label="Cambia area">
            <button className={area === 'invoices' ? 'active' : ''} onClick={() => setArea('invoices')}>
              <ReceiptText />Fatture
            </button>
            <button className={area === 'reviews' ? 'active' : ''} onClick={() => setArea('reviews')}>
              <MessageSquareText />Recensioni
            </button>
          </div>
        )}
        {uploaderOnly ? (
          <nav>
            <button className={page === 'uploader' ? 'active' : ''} onClick={() => { setPage('uploader'); setOpen(false); }}>
              <CloudUpload size={19} /><span>Carica fatture</span>
            </button>
          </nav>
        ) : area === 'invoices' ? (
          <nav>
            {nav.map(([id, label, Icon]) => (
              <button key={id} className={page === id ? 'active' : ''} onClick={() => { setPage(id); setOpen(false); }}>
                <Icon size={19} /><span>{label}</span>
              </button>
            ))}
          </nav>
        ) : (
          <nav>
            <button className="active"><LayoutDashboard size={19} /><span>Panoramica</span></button>
            <button><MessageSquareText size={19} /><span>Tutte le recensioni</span></button>
            <button><Sparkles size={19} /><span>Analisi IA</span></button>
            <button><Settings size={19} /><span>Impostazioni</span></button>
          </nav>
        )}
        <div className="local-status">
          <i />
          {user?.display_name || 'Utente'}
          <small>{user?.role_name} · PC locale</small>
          <button className="logout-btn" onClick={logout}><LogOut size={14} /> Esci</button>
        </div>
      </aside>
      {open && <button className="scrim" aria-label="Chiudi menu" onClick={() => setOpen(false)} />}
      <main>
        <button className="mobile-menu" onClick={() => setOpen(!open)}>{open ? <X /> : <Menu />}</button>
        {children}
      </main>
    </div>
  );
}
