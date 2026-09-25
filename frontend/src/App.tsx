import {useEffect, useState} from 'react';
import {Shell, Page} from './components/Shell';
import {AuthGate} from './components/AuthGate';
import Dashboard from './pages/Dashboard';
import {HistoryPage, Invoices, Products, Reports, SimplePage, Suppliers} from './pages/Lists';
import {AIPage, ImportPage, SettingsPage, SystemPage} from './pages/ImportAISettings';
import Reviews from './pages/Reviews';
import InvoiceEditor from './pages/InvoiceEditor';
import Warehouse from './pages/Warehouse';
import {StorageInboxPage, UploaderPage} from './pages/StoragePages';
import {currentUser, AuthUser} from './lib/api';
import './pages/InvoiceEditor.css';

function AppInner() {
  const [user, setUser] = useState<AuthUser | null>(() => currentUser());
  const uploaderOnly = user?.role_name === 'uploader';
  const [page, setPage] = useState<Page>(uploaderOnly ? 'uploader' : 'dashboard');
  const [editingInvoiceId, setEditingInvoiceId] = useState<number | null>(null);
  const [area, setAreaState] = useState<'invoices' | 'reviews'>(() =>
    localStorage.getItem('eye-supremo.area') === 'reviews' ? 'reviews' : 'invoices',
  );
  const [sidebarMode, setSidebarMode] = useState<'open' | 'collapsed' | 'pinned'>(() => {
    const stored = localStorage.getItem('eye-supremo.sidebar');
    return stored === 'collapsed' || stored === 'pinned' ? stored : 'open';
  });
  const [mobileOpen, setMobileOpen] = useState(false);
  const [storagePreview, setStoragePreview] = useState<any>(null);

  useEffect(() => {
    const sync = () => setUser(currentUser());
    window.addEventListener('eye-auth-expired', sync);
    sync();
    return () => window.removeEventListener('eye-auth-expired', sync);
  }, []);

  useEffect(() => {
    if (uploaderOnly && page !== 'uploader') setPage('uploader');
  }, [uploaderOnly, page]);

  useEffect(() => {
    localStorage.setItem('eye-supremo.sidebar', sidebarMode);
  }, [sidebarMode]);

  const setArea = (next: 'invoices' | 'reviews') => {
    localStorage.setItem('eye-supremo.area', next);
    setAreaState(next);
  };
  const navigate = (next: Page) => {
    if (uploaderOnly && next !== 'uploader') return;
    if (next === 'editor') setEditingInvoiceId(null);
    setPage(next);
  };
  const openInvoice = (id: number) => {
    setEditingInvoiceId(id);
    setPage('editor');
  };

  let content;
  if (uploaderOnly) content = <UploaderPage />;
  else if (area === 'reviews') content = <Reviews />;
  else
    switch (page) {
      case 'dashboard':
        content = <Dashboard go={navigate} />;
        break;
      case 'invoices':
        content = <Invoices onOpen={openInvoice} />;
        break;
      case 'editor':
        content = <InvoiceEditor invoiceId={editingInvoiceId} />;
        break;
      case 'products':
        content = <Products />;
        break;
      case 'warehouse':
        content = <Warehouse />;
        break;
      case 'suppliers':
        content = <Suppliers />;
        break;
      case 'import':
        content = <ImportPage initialPreview={storagePreview} onPreviewConsumed={() => setStoragePreview(null)} />;
        break;
      case 'storage-inbox':
        content = (
          <StorageInboxPage
            onPreview={(preview) => {
              setStoragePreview(preview);
              setPage('import');
            }}
          />
        );
        break;
      case 'central-catalog':
        // Unificato in Fatture (locale + Supabase)
        content = <Invoices onOpen={openInvoice} />;
        break;
      case 'ai':
        content = <AIPage />;
        break;
      case 'reports':
        content = <Reports />;
        break;
      case 'history':
        content = <HistoryPage />;
        break;
      case 'settings':
        content = <SettingsPage />;
        break;
      case 'system':
        content = <SystemPage />;
        break;
      case 'anomalies':
        content = <SimplePage title="Anomalie" subtitle="Controlli automatici su prezzi, quantità e coerenza" />;
        break;
      default:
        content = <SimplePage title="Categorie" subtitle="Classificazione dei prodotti e della spesa" />;
    }

  return (
    <Shell page={page} setPage={navigate} area={area} setArea={setArea} mode={sidebarMode} setMode={setSidebarMode} mobileOpen={mobileOpen} setMobileOpen={setMobileOpen} user={user}>
      {content}
    </Shell>
  );
}

export default function App() {
  return (
    <AuthGate>
      <AppInner />
    </AuthGate>
  );
}
