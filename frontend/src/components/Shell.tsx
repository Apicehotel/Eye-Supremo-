import {ReactNode} from 'react';
import {
  LayoutDashboard, FileText, FilePenLine, Package, Boxes, Users, Upload, Sparkles,
  ChartNoAxesCombined, History, TriangleAlert, Tags, Settings, MonitorCog, Menu, X,
  ReceiptText, MessageSquareText, CloudUpload, Inbox, LogOut, PanelLeftClose, PanelLeftOpen, Pin,
} from 'lucide-react';
import {clearAuth, AuthUser, currentSession} from '../lib/api';

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
  page, setPage, area, setArea, children, mode, setMode, mobileOpen, setMobileOpen, user,
}: {
  page: Page;
  setPage: (p: Page) => void;
  area: 'invoices' | 'reviews';
  setArea: (a: 'invoices' | 'reviews') => void;
  children: ReactNode;
  mode: 'open' | 'collapsed' | 'pinned';
  setMode: (v: 'open' | 'collapsed' | 'pinned') => void;
  mobileOpen: boolean;
  setMobileOpen: (v: boolean) => void;
  user: AuthUser | null;
}) {
  const uploaderOnly = user?.role_name === 'uploader';
  function logout() {
    const session = currentSession();
    fetch('/api/auth/logout', {method: 'POST', headers: {'X-Eye-Session': session || ''}}).finally(() => {
      clearAuth();
      window.dispatchEvent(new Event('eye-auth-expired'));
    });
  }

  return (
    <div className={`app-shell sidebar-${mode}`}>
      <aside className={`sidebar ${mode} ${mobileOpen ? 'mobile-open' : ''}`}>
        <div className="brand">
          <img className="brand-mark" src="/favicon-32.png" alt="Eye Supremo" width={28} height={28} />
          <div>
            <b>EYE</b> SUPREMO
            <span>{uploaderOnly ? 'Solo carico file' : area === 'invoices' ? 'Le tue fatture, più valore.' : 'Ascolta, rispondi, migliora.'}</span>
          </div>
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
            <button className={page === 'uploader' ? 'active' : ''} onClick={() => { setPage('uploader'); setMobileOpen(false); }}>
              <CloudUpload size={19} /><span>Carica fatture</span>
            </button>
          </nav>
        ) : area === 'invoices' ? (
          <nav>
            {nav.map(([id, label, Icon]) => (
              <button key={id} className={page === id ? 'active' : ''} onClick={() => { setPage(id); if (mode !== 'pinned') setMobileOpen(false); }}>
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
        <div className="sidebar-controls">
          <button title={mode === 'collapsed' ? 'Apri barra laterale' : 'Chiudi barra laterale'} aria-label={mode === 'collapsed' ? 'Apri barra laterale' : 'Chiudi barra laterale'} onClick={() => setMode(mode === 'collapsed' ? 'open' : 'collapsed')}>
            {mode === 'collapsed' ? <PanelLeftOpen size={18} /> : <PanelLeftClose size={18} />}
            <span>{mode === 'collapsed' ? 'Apri' : 'Riduci'}</span>
          </button>
          <button className={mode === 'pinned' ? 'active' : ''} title={mode === 'pinned' ? 'Sblocca barra laterale' : 'Fissa barra laterale'} aria-label={mode === 'pinned' ? 'Sblocca barra laterale' : 'Fissa barra laterale'} onClick={() => setMode(mode === 'pinned' ? 'open' : 'pinned')}>
            <Pin size={16} /><span>{mode === 'pinned' ? 'Fissata' : 'Fissa'}</span>
          </button>
        </div>
      </aside>
      {mobileOpen && <button className="scrim" aria-label="Chiudi menu" onClick={() => setMobileOpen(false)} />}
      <main>
        <button className="mobile-menu" onClick={() => setMobileOpen(!mobileOpen)}>{mobileOpen ? <X /> : <Menu />}</button>
        {children}
      </main>
    </div>
  );
}
