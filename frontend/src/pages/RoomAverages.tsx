import {Fragment, useMemo, useState} from 'react';
import {BedDouble, Search, TriangleAlert} from 'lucide-react';
import {Status} from '../components/UI';
import {GIO_ROOM_GROUPS, type FloorFilter, type RoomGroupKey} from '../lib/roomGroups';
import {SOURCES, roomStatus, sourceKey, sourceOverview, type RoomAverage, type SourceKey} from '../lib/roomAverages';

export type RoomReviewItem = {id: number | string; source: string | null; date: string; rating: number | null; author: string | null; text: string; scores: Record<string, number>; tags: {category: string; polarity: string}[]};

type Sort = 'room_asc' | `${'Booking' | 'Google' | 'TripAdvisor'}_${'desc' | 'asc'}` | 'count_desc';
const fmt = (value: number) => value.toFixed(2).replace('.', ',');
const scaleOf = (key: SourceKey) => SOURCES.find(s => s.key === key)!.scale;

export default function RoomAverages({reviewsByRoom, rows, invalid, scopeLabel, categories, category, onCategory, group, onGroup, floor, onFloor}: {reviewsByRoom: Record<string, RoomReviewItem[]>; rows: RoomAverage[]; invalid: number; scopeLabel: string; categories: string[]; category: string; onCategory: (value: string) => void; group: RoomGroupKey; onGroup: (value: RoomGroupKey) => void; floor: FloorFilter; onFloor: (value: FloorFilter) => void}) {
  const [query, setQuery] = useState(''), [sort, setSort] = useState<Sort>('room_asc'), [minReviews, setMinReviews] = useState(1), [open, setOpen] = useState<string | null>(null), [openSource, setOpenSource] = useState<SourceKey | 'all'>('all');
  const toggle = (key: string, src: SourceKey | 'all') => { if (open === key && openSource === src) setOpen(null); else { setOpen(key); setOpenSource(src); } };
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = rows.filter(r => r.total >= minReviews && (!q || `${r.room} ${r.hotel}`.toLowerCase().includes(q)));
    const bySourceSort = (key: SourceKey, dir: 1 | -1) => (a: RoomAverage, b: RoomAverage) => {
      const x = a.bySource[key]?.average, y = b.bySource[key]?.average;
      if (x === undefined && y === undefined) return 0;
      if (x === undefined) return 1;
      if (y === undefined) return -1;
      return (x - y) * dir;
    };
    const compare = sort === 'count_desc' ? (a: RoomAverage, b: RoomAverage) => b.total - a.total
      : sort === 'room_asc' ? (a: RoomAverage, b: RoomAverage) => a.room.localeCompare(b.room, 'it', {numeric: true}) || a.hotel.localeCompare(b.hotel)
      : bySourceSort(sort.split('_')[0] as SourceKey, sort.endsWith('_desc') ? -1 : 1);
    return [...filtered].sort(compare);
  }, [rows, query, sort, minReviews]);
  const overview = useMemo(() => sourceOverview(visible), [visible]);

  return <section className="room-averages">
    <section className="review-kpis">
      <article className="kpi"><BedDouble/><div><span>Camere con voto</span><strong>{visible.length}</strong><small>{scopeLabel}</small></div></article>
      {SOURCES.map(({key, scale}) => <article className="kpi" key={key}><div><span>Media {key}</span><strong>{overview[key] ? `${fmt(overview[key]!.average)} / ${scale}` : '—'}</strong><small>{overview[key] ? `${overview[key]!.count} voti` : 'nessun voto'}</small></div></article>)}
    </section>
    <section className="panel room-averages-panel">
      <div className="panel-title"><div><h2>{category ? `Media ${category} per camera` : 'Media voti per camera'}</h2><span>Una media per fonte, ciascuna sulla sua scala (Booking su 10, Google e TripAdvisor su 5) · incluse le recensioni solo voto</span></div><Status tone="ok">{visible.length} camere</Status></div>
      {invalid > 0 && <p className="room-averages-warning"><TriangleAlert size={15}/> {invalid} {invalid === 1 ? 'voto fuori scala ignorato' : 'voti fuori scala ignorati'}: probabile errore di lettura in importazione (per esempio un giorno della data scambiato per voto).</p>}
      <div className="room-averages-tools">
        <label className="global-search review-search"><Search/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Cerca camera o hotel…"/></label>
        <select className="review-control" aria-label="Filtra per zona camere" value={group} onChange={e => onGroup(e.target.value as RoomGroupKey)}>
          <option value="all">Tutte le camere</option>
          <option value="cantine">Tutte le Cantine Wine</option>
          {GIO_ROOM_GROUPS.map(g => <option key={g.key} value={g.key}>{g.label}</option>)}
        </select>
        <select className="review-control" aria-label="Filtra per pavimento" value={floor} onChange={e => onFloor(e.target.value as FloorFilter)}>
          <option value="all">Moquette e non</option>
          <option value="moquette">Con moquette</option>
          <option value="no-moquette">Senza moquette</option>
        </select>
        <select className="review-control" aria-label="Voto per tag" value={category} onChange={e => onCategory(e.target.value)}>
          <option value="">Voto generale</option>
          {categories.map(name => <option key={name} value={name}>{name}</option>)}
        </select>
        <select className="review-control" aria-label="Ordina camere" value={sort} onChange={e => setSort(e.target.value as Sort)}>
          <option value="room_asc">Numero camera</option>
          {SOURCES.map(({key}) => <option key={`${key}d`} value={`${key}_desc`}>Media {key} più alta</option>)}
          {SOURCES.map(({key}) => <option key={`${key}a`} value={`${key}_asc`}>Media {key} più bassa</option>)}
          <option value="count_desc">Più recensioni</option>
        </select>
        <select className="review-control" aria-label="Recensioni minime" value={minReviews} onChange={e => setMinReviews(Number(e.target.value))}>
          <option value={1}>Da 1 voto</option><option value={2}>Almeno 2 voti</option><option value={3}>Almeno 3 voti</option><option value={5}>Almeno 5 voti</option>
        </select>
      </div>
      {visible.length ? <div className="table-wrap"><table className="room-averages-table">
        <thead><tr><th>Camera</th><th>Hotel</th>{SOURCES.map(({key, scale}) => <th key={key}>{key} / {scale}</th>)}<th>Ultimo voto</th></tr></thead>
        <tbody>{visible.map(r => {
          const key = `${r.hotel_code}|${r.room}`;
          const isOpen = open === key;
          const list = (reviewsByRoom[key] || []).filter(x => openSource === 'all' || sourceKey(x.source) === openSource);
          return <Fragment key={key}>
            <tr className={`room-row-clickable${isOpen ? ' room-row-open' : ''}`} onClick={() => toggle(key, 'all')} tabIndex={0} onKeyDown={e => { if (e.key === 'Enter' || e.key === ' ') { e.preventDefault(); toggle(key, 'all'); } }} aria-expanded={isOpen}>
              <td><b>{isOpen ? '▾' : '▸'} {r.room}</b></td><td>{r.hotel}</td>
              {SOURCES.map(({key: sk}) => {
                const entry = r.bySource[sk];
                if (!entry) return <td key={sk} className="room-average-empty">—</td>;
                const status = roomStatus(entry.average, scaleOf(sk));
                return <td key={sk} className="room-average-source" onClick={e => { e.stopPropagation(); toggle(key, sk); }} title={`Vedi recensioni ${sk}`}><div className="room-average-cell"><strong className={`timeline-status-${status}`}>{fmt(entry.average)}</strong><small>{entry.count} {entry.count === 1 ? 'voto' : 'voti'}{entry.count > 1 ? ` · ${fmt(entry.min)}–${fmt(entry.max)}` : ''}</small></div></td>;
              })}
              <td>{r.lastDate}</td>
            </tr>
            {isOpen && <tr key={`${key}-d`} className="room-detail-row"><td colSpan={3 + SOURCES.length}>
              <div className="room-detail-head"><b>Camera {r.room} · {openSource === 'all' ? 'tutte le fonti' : openSource}</b><span>{list.length} {list.length === 1 ? 'recensione' : 'recensioni'}</span>{openSource !== 'all' && <button className="secondary-btn" onClick={() => setOpenSource('all')}>Mostra tutte</button>}<button className="secondary-btn" onClick={() => setOpen(null)}>Chiudi</button></div>
              {list.length ? <div className="room-detail-list">{list.map(x => <article key={x.id}>
                <header><b>{x.source || 'Fonte non indicata'}</b><span>{x.date}{x.rating !== null ? ` · ${String(x.rating).replace('.', ',')}${sourceKey(x.source) === 'Booking' ? '/10' : '/5'}` : ''}{x.author ? ` · ${x.author}` : ''}</span></header>
                {Object.keys(x.scores).length > 0 && <div className="score-chips">{Object.entries(x.scores).map(([name, v]) => <span key={name}>{name} {String(v).replace('.', ',')}</span>)}</div>}
                <p>{x.text || 'Solo voto, nessun testo.'}</p>
              </article>)}</div> : <div className="empty"><span>Nessuna recensione per questa fonte.</span></div>}
            </td></tr>}
          </Fragment>;
        })}</tbody>
      </table></div> : <div className="empty"><span>Nessuna camera con voti per questa selezione.</span></div>}
    </section>
  </section>;
}
