import {useEffect, useMemo, useState} from 'react';
import {MessageSquareText, Star, Store, Reply, Search, ExternalLink, Loader2} from 'lucide-react';
import {PageHeader, Status} from '../components/UI';
import {api} from '../lib/api';

type Review = {
  id: string;
  hotelId: string;
  author: string;
  source: string;
  rating: number;
  rating_missing?: boolean;
  date: string;
  text: string;
  status: string;
  room_code?: string | null;
};

type HotelStat = {
  id: string;
  name: string;
  short: string;
  score: string;
  count: number;
  avg_rating?: number | null;
};

const FALLBACK_HOTELS: HotelStat[] = [
  {id: 'all', name: 'Tutti gli hotel', short: 'Tutti', score: '—', count: 0},
  {id: 'hotelgio', name: 'Hotel Giò', short: 'Hotel Giò', score: '—', count: 0},
  {id: 'chocohotel', name: 'Chocohotel', short: 'Chocohotel', score: '—', count: 0},
  {id: 'brigantino', name: 'Hotel Il Brigantino', short: 'Il Brigantino', score: '—', count: 0},
];

export default function Reviews() {
  const [query, setQuery] = useState('');
  const [filter, setFilter] = useState('Tutte');
  const [hotel, setHotel] = useState('all');
  const [reviews, setReviews] = useState<Review[]>([]);
  const [hotels, setHotels] = useState<HotelStat[]>(FALLBACK_HOTELS);
  const [total, setTotal] = useState(0);
  const [busy, setBusy] = useState(true);
  const [error, setError] = useState('');

  useEffect(() => {
    let alive = true;
    (async () => {
      setBusy(true);
      setError('');
      try {
        const data = await api<{
          items: Review[];
          hotels: HotelStat[];
          total: number;
          configured: boolean;
        }>('/storage/central/reviews');
        if (!alive) return;
        setReviews(data.items || []);
        setHotels(data.hotels?.length ? data.hotels : FALLBACK_HOTELS);
        setTotal(data.total || data.items?.length || 0);
      } catch (e: any) {
        if (!alive) return;
        const msg = String(e?.message || e);
        setError(
          msg.includes('503') || msg.includes('non configurate')
            ? 'Configura URL + chiave anon e RANDFATTURE_SUPABASE_CENTRAL_PIN nel .env per leggere eye_central_reviews.'
            : msg,
        );
        setReviews([]);
      } finally {
        if (alive) setBusy(false);
      }
    })();
    return () => {
      alive = false;
    };
  }, []);

  const selected = hotels.find((h) => h.id === hotel) || hotels[0];
  const visible = useMemo(
    () =>
      reviews.filter(
        (r) =>
          (hotel === 'all' || r.hotelId === hotel) &&
          (filter === 'Tutte' || (filter === 'Da rispondere' && r.status === 'Da rispondere')) &&
          (r.author + ' ' + r.text + ' ' + r.source).toLowerCase().includes(query.toLowerCase()),
      ),
    [reviews, query, filter, hotel],
  );

  const ratingBars = useMemo(() => {
    const pool = hotel === 'all' ? reviews : reviews.filter((r) => r.hotelId === hotel);
    const withRating = pool.filter((r) => !r.rating_missing && r.rating > 0);
    const totalR = withRating.length || 1;
    return [5, 4, 3, 2, 1].map((stars) => {
      const n = withRating.filter((r) => Math.round(r.rating) === stars).length;
      return {stars, pct: Math.round((n / totalR) * 100), n};
    });
  }, [reviews, hotel]);

  const hotelName = (id: string) => hotels.find((h) => h.id === id)?.name || id;

  return (
    <>
      <PageHeader
        title="Recensioni"
        subtitle={
          busy
            ? 'Caricamento da Supabase MultiHotel…'
            : total
              ? `${total} recensioni in eye_central_reviews · Giò / Choco / Brigantino`
              : 'Monitora i feedback da Supabase MultiHotel'
        }
      >
        <label className="global-search review-search">
          <Search />
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Cerca nelle recensioni…"
          />
        </label>
      </PageHeader>

      {error && <div className="error">{error}</div>}

      <section className="hotel-selector" aria-label="Classifica recensioni per hotel">
        {hotels.map((h) => (
          <button
            key={h.id}
            className={hotel === h.id ? 'active' : ''}
            onClick={() => setHotel(h.id)}
          >
            <span>{h.short}</span>
            <small>
              {h.count} recensioni · {h.score} ★
            </small>
          </button>
        ))}
      </section>

      <section className="review-kpis">
        <article className="kpi">
          <MessageSquareText />
          <div>
            <span>Recensioni · {selected.short}</span>
            <strong>{busy ? '…' : selected.count}</strong>
            <small>Archivio MultiHotel</small>
          </div>
        </article>
        <article className="kpi">
          <Star />
          <div>
            <span>Valutazione media</span>
            <strong>{busy ? '…' : selected.score}</strong>
            <small>
              {selected.avg_rating != null ? 'Media sulle recensioni con voto' : 'Nessun voto disponibile'}
            </small>
          </div>
        </article>
        <article className="kpi">
          <Reply />
          <div>
            <span>Da rispondere</span>
            <strong>0</strong>
            <small>stato risposta non ancora sincronizzato</small>
          </div>
        </article>
        <article className="kpi">
          <Store />
          <div>
            <span>Struttura</span>
            <strong className="hotel-kpi-name">{selected.short}</strong>
            <small>{hotel === 'all' ? '3 hotel Apicehotel' : 'Dati isolati per hotel'}</small>
          </div>
        </article>
      </section>

      <section className="reviews-layout">
        <article className="panel reviews-panel">
          <div className="panel-title review-toolbar">
            <div>
              <h2>Recensioni recenti</h2>
              <span>
                {selected.name} · {visible.length} visibili
              </span>
            </div>
            <div className="review-filters">
              <button className={filter === 'Tutte' ? 'active' : ''} onClick={() => setFilter('Tutte')}>
                Tutte
              </button>
              <button
                className={filter === 'Da rispondere' ? 'active' : ''}
                onClick={() => setFilter('Da rispondere')}
              >
                Da rispondere
              </button>
            </div>
          </div>
          <div className="review-list">
            {busy && (
              <div className="empty">
                <Loader2 className="spin" />
                <strong>Lettura da Supabase…</strong>
                <span>RPC eye_central_review_page</span>
              </div>
            )}
            {!busy &&
              visible.map((r) => (
                <article className="review-row" key={r.id}>
                  <div className="review-avatar">{(r.author[0] || '?').toUpperCase()}</div>
                  <div className="review-body">
                    <div className="review-meta">
                      <b>{r.author}</b>
                      <span>
                        {r.source} · {r.date || '—'}
                        {r.room_code ? ` · cam. ${r.room_code}` : ''}
                      </span>
                    </div>
                    <div className="review-hotel">{hotelName(r.hotelId)}</div>
                    <div
                      className="stars"
                      aria-label={r.rating_missing ? 'voto assente' : `${r.rating} stelle`}
                    >
                      {[1, 2, 3, 4, 5].map((n) => (
                        <Star
                          key={n}
                          size={14}
                          fill={!r.rating_missing && n <= Math.round(r.rating) ? 'currentColor' : 'none'}
                          className={!r.rating_missing && n <= Math.round(r.rating) ? 'filled' : ''}
                        />
                      ))}
                    </div>
                    <p>{r.text}</p>
                    <div className="review-actions">
                      <Status tone="ok">{r.status}</Status>
                      <button type="button" disabled>
                        <Reply size={14} />
                        Rispondi
                      </button>
                      <button type="button" disabled>
                        <ExternalLink size={14} />
                        Apri fonte
                      </button>
                    </div>
                  </div>
                </article>
              ))}
            {!busy && !visible.length && (
              <div className="empty">
                <strong>Nessuna recensione</strong>
                <span>
                  {error
                    ? 'Collega MultiHotel nel .env per leggere eye_central_reviews.'
                    : `Nessun risultato per ${selected.name}.`}
                </span>
              </div>
            )}
          </div>
        </article>
        <aside className="panel review-summary">
          <h2>Riepilogo · {selected.short}</h2>
          <div className="sentiment-score">
            <strong>{selected.score}</strong>
            <span>{selected.count ? 'media voti' : 'Nessun dato'}</span>
          </div>
          <div className="rating-bars">
            {ratingBars.map(({stars, pct}) => (
              <div key={stars}>
                <span>{stars} ★</span>
                <i>
                  <b style={{width: `${pct}%`}} />
                </i>
                <small>{pct}%</small>
              </div>
            ))}
          </div>
          <hr />
          <h3>Fonti</h3>
          <div className="empty">
            <span>
              {busy
                ? '…'
                : total
                  ? 'Booking, TripAdvisor, Google e import TXT da digest MSG.'
                  : 'Disponibili dopo il collegamento a Supabase.'}
            </span>
          </div>
        </aside>
      </section>
    </>
  );
}
