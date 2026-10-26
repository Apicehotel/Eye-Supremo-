import {useEffect, useState} from 'react';
import {eyeApi} from '../lib/api';
import {normalizedReviewRating} from '../lib/reviewRating';
import type {Page} from './Shell';

type Tile = {key: string; label: string; value: string; hint: string; shape: string; go: () => void};
type Listing = {total?: number; count?: number; items?: unknown[]};
type Rev = {rating: number | null; source: string | null};

const fmt = (n: number | null | undefined) => (n === null || n === undefined ? '–' : n.toLocaleString('it-IT'));

export function OnlineHome({area, go, openReviews}: {area: 'invoices' | 'reviews'; go: (p: Page) => void; openReviews: (view: string) => void}) {
  const [data, setData] = useState<{invoices: number | null; suppliers: number | null; products: number | null; reviews: number | null; avg: number | null; rooms: number | null; best: string; worst: string}>({invoices: null, suppliers: null, products: null, reviews: null, avg: null, rooms: null, best: '–', worst: '–'});
  useEffect(() => {
    let alive = true;
    const patch = (p: Partial<typeof data>) => alive && setData(d => ({...d, ...p}));
    if (area === 'invoices') {
      eyeApi<Listing>('/central/invoices?limit=1').then(r => patch({invoices: r.total ?? r.count ?? null})).catch(() => {});
      eyeApi<Listing>('/central/suppliers').then(r => patch({suppliers: r.count ?? r.total ?? r.items?.length ?? null})).catch(() => {});
      eyeApi<unknown[]>('/products?limit=500').then(r => patch({products: r.length})).catch(() => {});
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
    {key: 'a', label: 'Fatture', value: fmt(data.invoices), hint: 'archivio centrale', shape: 'blob-a', go: () => go('invoices')},
    {key: 'b', label: 'Fornitori', value: fmt(data.suppliers), hint: 'in anagrafica', shape: 'blob-b', go: () => go('suppliers')},
    {key: 'c', label: 'Prodotti', value: fmt(data.products), hint: 'nel catalogo', shape: 'blob-c', go: () => go('products')},
    {key: 'd', label: 'Utenti', value: '', hint: 'profili e PIN', shape: 'blob-d', go: () => go('users')},
  ] : [
    {key: 'a', label: 'Recensioni', value: fmt(data.reviews), hint: 'valide', shape: 'blob-a', go: () => openReviews('reviews')},
    {key: 'b', label: 'Voto medio', value: data.avg === null ? '–' : data.avg.toFixed(2).replace('.', ','), hint: 'su 10', shape: 'blob-b', go: () => openReviews('overview')},
    {key: 'c', label: 'Camera top', value: data.best, hint: 'ranking', shape: 'blob-c', go: () => openReviews('ranking')},
    {key: 'd', label: 'Da migliorare', value: data.worst, hint: 'camera critica', shape: 'blob-d', go: () => openReviews('ranking')},
  ];
  return <section className="home-grid" aria-label={area === 'invoices' ? 'Home fatture' : 'Home recensioni'}>
    {tiles.map(t => <button key={t.key} className={`home-tile ${t.shape}`} onClick={t.go}>
      <small>{t.label}</small><strong>{t.value || '→'}</strong><em>{t.hint}</em>
    </button>)}
  </section>;
}
