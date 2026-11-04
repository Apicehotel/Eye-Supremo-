import {useEffect, useState} from 'react';
import {AlertTriangle, ArrowLeftRight, Building2, FileText, Gauge, Package, Star, Trophy, Users} from 'lucide-react';
import type {LucideIcon} from 'lucide-react';
import {eyeApi} from '../lib/api';
import {normalizedReviewRating} from '../lib/reviewRating';
import type {Page} from './Shell';

type Tile = {key: string; label: string; value: string; hint: string; icon: LucideIcon; go: () => void};
type Listing = {total?: number; count?: number; items?: any[]};
type Rev = {rating: number | null; source: string | null};
type RecentInvoice = {invoice_number?: string; invoice_date?: string; supplier_name?: string; total?: number};

const fmt = (n: number | null | undefined) => (n === null || n === undefined ? '–' : n.toLocaleString('it-IT'));

export function OnlineHome({area, go, openReviews}: {area: 'invoices' | 'reviews'; go: (p: Page) => void; openReviews: (view: string) => void}) {
  const [data, setData] = useState<{invoices: number | null; suppliers: number | null; products: number | null; reviews: number | null; avg: number | null; rooms: number | null; best: string; worst: string; latest: RecentInvoice[]}>({invoices: null, suppliers: null, products: null, reviews: null, avg: null, rooms: null, best: '–', worst: '–', latest: []});
  useEffect(() => {
    let alive = true;
    const patch = (p: Partial<typeof data>) => alive && setData(d => ({...d, ...p}));
    if (area === 'invoices') {
      eyeApi<Listing>('/central/invoices?limit=1').then(r => patch({invoices: r.total ?? r.count ?? null})).catch(() => {});
      eyeApi<Listing>('/central/invoices?limit=5&offset=0').then(r => patch({latest: (r.items || []).slice(0, 5)})).catch(() => {});
      eyeApi<Listing>('/central/suppliers').then(r => patch({suppliers: r.count ?? r.total ?? r.items?.length ?? null})).catch(() => {});
      eyeApi<any>('/products?limit=500').then(r => patch({products: Array.isArray(r) ? r.length : (r.total ?? r.items?.length ?? null)})).catch(() => {});
    } else {
      eyeApi<Rev[]>('/reviews').then(r => {
        const votes = r.map(x => normalizedReviewRating(x)).filter((x): x is number => x !== null);
        patch({reviews: r.length, avg: votes.length ? votes.reduce((a, b) => a + b, 0) / votes.length : null});
      }).catch(() => {});
      eyeApi<{best_rooms: {room: string}[]; worst_rooms: {room: string}[]}>('/rankings?limit=1').then(r => patch({best: r.best_rooms?.[0]?.room ?? '–', worst: r.worst_rooms?.[0]?.room ?? '–'})).catch(() => {});
      eyeApi<{rooms: unknown[]}>('/rankings/timeline').then(r => patch({rooms: r.rooms.length})).catch(() => {});
    }
    return () => {alive = false;};
  }, [area]);
  const tiles: Tile[] = area === 'invoices' ? [
    {key: 'a', label: 'Fatture', value: fmt(data.invoices), hint: 'archivio centrale', icon: FileText, go: () => go('invoices')},
    {key: 'b', label: 'Fornitori', value: fmt(data.suppliers), hint: 'in anagrafica', icon: Building2, go: () => go('suppliers')},
    {key: 'c', label: 'Prodotti', value: fmt(data.products), hint: 'nel catalogo', icon: Package, go: () => go('products')},
    {key: 'd', label: 'Utenti', value: '', hint: 'profili e PIN', icon: Users, go: () => go('users')},
  ] : [
    {key: 'a', label: 'Recensioni', value: fmt(data.reviews), hint: 'valide', icon: Star, go: () => openReviews('reviews')},
    {key: 'b', label: 'Voto medio', value: data.avg === null ? '–' : data.avg.toFixed(2).replace('.', ','), hint: 'su 10', icon: Gauge, go: () => openReviews('overview')},
    {key: 'c', label: 'Camera top', value: data.best, hint: 'ranking', icon: Trophy, go: () => openReviews('ranking')},
    {key: 'd', label: 'Da migliorare', value: data.worst, hint: 'camera critica', icon: AlertTriangle, go: () => openReviews('ranking')},
  ];
  const formatDate = (value?: string) => value ? new Intl.DateTimeFormat('it-IT').format(new Date(value)) : '—';
  const formatMoney = (value?: number) => value == null ? '—' : new Intl.NumberFormat('it-IT', {style: 'currency', currency: 'EUR'}).format(Number(value));
  return <section className="online-home" aria-label={area === 'invoices' ? 'Home fatture' : 'Home recensioni'}>
    <div className="online-home-heading"><div><h1>{area === 'invoices' ? 'Gestione acquisti' : 'Controllo recensioni'}</h1><p>Scegli una sezione per consultare i dati.</p></div><span>Archivio centrale</span></div>
    <div className="home-grid">{tiles.map(t => <button key={t.key} className="home-tile" onClick={t.go}>
      <span className="home-tile-icon"><t.icon size={18}/></span><span className="home-tile-copy"><small>{t.label}</small><strong>{t.value || 'Apri'}</strong><em>{t.hint}</em></span><span className="home-tile-arrow">→</span>
    </button>)}</div>
    {area === 'invoices' ? <div className="online-home-columns">
      <section className="home-panel"><div className="home-panel-heading"><div><h2>Ultime fatture</h2><p>Gli ultimi documenti presenti nell’archivio centrale.</p></div><button className="home-link" onClick={() => go('invoices')}>Vedi tutte →</button></div><div className="home-invoice-list">{data.latest.length ? data.latest.map((invoice, index) => <button className="home-invoice-row" key={`${invoice.invoice_number}-${index}`} onClick={() => go('invoices')}><span className="home-invoice-date">{formatDate(invoice.invoice_date)}</span><span className="home-invoice-main"><b>{invoice.supplier_name || 'Fornitore non indicato'}</b><small>{invoice.invoice_number || 'Fattura senza numero'}</small></span><strong>{formatMoney(invoice.total)}</strong><span className="home-row-arrow">→</span></button>) : <div className="home-empty">Caricamento fatture recenti…</div>}</div></section>
      <section className="home-panel home-actions"><div className="home-panel-heading"><div><h2>Accesso rapido</h2><p>Le attività più usate.</p></div></div><button onClick={() => go('invoices')}><FileText size={18}/><span><b>Cerca una fattura</b><small>Numero, fornitore o data</small></span><span>→</span></button><button onClick={() => go('suppliers')}><Building2 size={18}/><span><b>Consulta fornitori</b><small>Anagrafiche e storico commerciale</small></span><span>→</span></button><button onClick={() => go('history-report')}><ArrowLeftRight size={18}/><span><b>Confronto prezzi</b><small>Fornitori, medie e variazioni nel tempo</small></span><span>→</span></button><button onClick={() => go('products')}><Package size={18}/><span><b>Apri catalogo prodotti</b><small>Articoli e prezzi disponibili</small></span><span>→</span></button></section>
    </div> : <div className="online-home-columns">
      <section className="home-panel"><div className="home-panel-heading"><div><h2>Panoramica recensioni</h2><p>Indicatori principali dell’archivio recensioni.</p></div><button className="home-link" onClick={() => openReviews('overview')}>Apri analisi →</button></div><div className="home-review-summary"><div><span>Recensioni valide</span><b>{fmt(data.reviews)}</b></div><div><span>Voto medio</span><b>{data.avg === null ? '–' : data.avg.toFixed(2).replace('.', ',')}<small>/10</small></b></div><div><span>Camere analizzate</span><b>{fmt(data.rooms)}</b></div></div></section>
      <section className="home-panel home-actions"><div className="home-panel-heading"><div><h2>Accesso rapido</h2><p>Vai direttamente alla lettura dei risultati.</p></div></div><button onClick={() => openReviews('reviews')}><Star size={18}/><span><b>Leggi le recensioni</b><small>Testi, fonti e voti</small></span><span>→</span></button><button onClick={() => openReviews('ranking')}><Trophy size={18}/><span><b>Apri il ranking</b><small>Camere migliori e critiche</small></span><span>→</span></button></section>
    </div>}
  </section>;
}
