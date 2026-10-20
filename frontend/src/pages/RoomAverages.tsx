import {useMemo, useState} from 'react';
import {BedDouble, Search, Star, Trophy, TriangleAlert} from 'lucide-react';
import {Status} from '../components/UI';
import {roomStatus, type RoomAverage} from '../lib/roomAverages';

type Sort = 'avg_desc' | 'avg_asc' | 'count_desc' | 'room_asc';
const fmt = (value: number) => value.toFixed(2).replace('.', ',');

export default function RoomAverages({rows, scopeLabel}: {rows: RoomAverage[]; scopeLabel: string}) {
  const [query, setQuery] = useState(''), [sort, setSort] = useState<Sort>('avg_desc'), [minReviews, setMinReviews] = useState(1);
  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const filtered = rows.filter(r => r.reviews >= minReviews && (!q || `${r.room} ${r.hotel}`.toLowerCase().includes(q)));
    return [...filtered].sort((a, b) => sort === 'avg_asc' ? a.average - b.average
      : sort === 'count_desc' ? b.reviews - a.reviews || b.average - a.average
      : sort === 'room_asc' ? a.room.localeCompare(b.room, 'it', {numeric: true}) || a.hotel.localeCompare(b.hotel)
      : b.average - a.average || b.reviews - a.reviews);
  }, [rows, query, sort, minReviews]);
  const totalReviews = visible.reduce((sum, r) => sum + r.reviews, 0);
  const overall = totalReviews ? visible.reduce((sum, r) => sum + r.average * r.reviews, 0) / totalReviews : null;
  const best = visible.length ? visible.reduce((x, y) => y.average > x.average ? y : x) : null;
  const worst = visible.length ? visible.reduce((x, y) => y.average < x.average ? y : x) : null;

  return <section className="room-averages">
    <section className="review-kpis">
      <article className="kpi"><BedDouble/><div><span>Camere con voto</span><strong>{visible.length}</strong><small>{scopeLabel}</small></div></article>
      <article className="kpi"><Star/><div><span>Media complessiva</span><strong>{overall === null ? '—' : `${fmt(overall)} / 10`}</strong><small>{totalReviews} recensioni con voto</small></div></article>
      <article className="kpi"><Trophy/><div><span>Camera migliore</span><strong>{best ? `${best.room} · ${fmt(best.average)}` : '—'}</strong><small>{best?.hotel || 'nessun dato'}</small></div></article>
      <article className="kpi"><TriangleAlert/><div><span>Camera più bassa</span><strong>{worst ? `${worst.room} · ${fmt(worst.average)}` : '—'}</strong><small>{worst?.hotel || 'nessun dato'}</small></div></article>
    </section>
    <section className="panel room-averages-panel">
      <div className="panel-title"><div><h2>Media voti per camera</h2><span>Voti normalizzati su scala 10 (Google e TripAdvisor ×2) · incluse le recensioni solo voto</span></div><Status tone="ok">{visible.length} camere</Status></div>
      <div className="room-averages-tools">
        <label className="global-search review-search"><Search/><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Cerca camera o hotel…"/></label>
        <select className="review-control" aria-label="Ordina camere" value={sort} onChange={e => setSort(e.target.value as Sort)}>
          <option value="avg_desc">Media più alta</option><option value="avg_asc">Media più bassa</option><option value="count_desc">Più recensioni</option><option value="room_asc">Numero camera</option>
        </select>
        <select className="review-control" aria-label="Recensioni minime" value={minReviews} onChange={e => setMinReviews(Number(e.target.value))}>
          <option value={1}>Da 1 recensione</option><option value={2}>Almeno 2</option><option value={3}>Almeno 3</option><option value={5}>Almeno 5</option>
        </select>
      </div>
      {visible.length ? <div className="table-wrap"><table className="room-averages-table">
        <thead><tr><th>Camera</th><th>Hotel</th><th>Media / 10</th><th>Recensioni</th><th>Min – Max</th><th>Ultimo voto</th><th>Fonti</th></tr></thead>
        <tbody>{visible.map(r => {
          const status = roomStatus(r.average);
          return <tr key={`${r.hotel_code}-${r.room}`}>
            <td><b>{r.room}</b></td><td>{r.hotel}</td>
            <td><div className="room-average-cell"><strong className={`timeline-status-${status}`}>{fmt(r.average)}</strong><span className="room-average-bar"><i className={`room-average-fill room-average-${status}`} style={{width: `${Math.min(100, r.average * 10)}%`}}/></span></div></td>
            <td>{r.reviews}</td><td>{fmt(r.min)} – {fmt(r.max)}</td><td>{r.lastDate}</td>
            <td>{r.sources.map(s => `${s.source} ${s.count}`).join(' · ')}</td>
          </tr>;
        })}</tbody>
      </table></div> : <div className="empty"><span>Nessuna camera con voti per questa selezione.</span></div>}
    </section>
  </section>;
}
