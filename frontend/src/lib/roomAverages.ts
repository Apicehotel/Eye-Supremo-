export type SourceKey = 'Booking' | 'Google' | 'TripAdvisor';
export const SOURCES: {key: SourceKey; scale: 5 | 10}[] = [
  {key: 'Booking', scale: 10},
  {key: 'Google', scale: 5},
  {key: 'TripAdvisor', scale: 5},
];

export function sourceKey(source: string | null | undefined): SourceKey | null {
  const name = (source || '').trim().toLowerCase();
  if (name === 'booking' || name === 'booking.com') return 'Booking';
  if (name === 'google') return 'Google';
  if (name === 'tripadvisor') return 'TripAdvisor';
  return null;
}

export type RoomRatingInput = {
  hotel: string;
  hotel_code: string;
  room: string | null;
  source: string | null;
  date: string;
  /** Voto originale, sulla scala della sua fonte (Booking 0–10, Google/TripAdvisor 0–5). */
  rating: number | null;
  /** Voti per tag letti nella recensione (Staff, Pulizia, Colazione…), stessa scala del voto. */
  scores?: Record<string, number> | null;
};

/** Tag con almeno un voto, in ordine alfabetico. */
export function scoreCategories(items: {scores?: Record<string, number> | null}[]): string[] {
  const names = new Set<string>();
  for (const item of items) for (const name of Object.keys(item.scores || {})) names.add(name);
  return [...names].sort((a, b) => a.localeCompare(b, 'it'));
}

export type SourceAverage = {average: number; count: number; min: number; max: number};

export type RoomAverage = {
  hotel: string;
  hotel_code: string;
  room: string;
  lastDate: string;
  total: number;
  bySource: Record<SourceKey, SourceAverage | null>;
};

export type RoomAveragesResult = {
  rows: RoomAverage[];
  /** Voti fuori scala ignorati (es. un giorno di calendario letto per errore come voto). */
  invalid: number;
};

export type RoomStatus = 'ok' | 'monitorare' | 'attenzione';

/** Stato della media: soglie sulla scala 10, riportando il voto alla sua scala. */
export function roomStatus(average: number, scale: 5 | 10): RoomStatus {
  const onTen = average / scale * 10;
  return onTen < 6 ? 'attenzione' : onTen < 7.5 ? 'monitorare' : 'ok';
}

const round2 = (value: number) => Math.round(value * 100) / 100;

/** Medie per camera, tenute separate per fonte: nessun voto di scale diverse viene mescolato. */
export function roomAverages(items: RoomRatingInput[], category: string | null = null): RoomAveragesResult {
  type Group = {hotel: string; hotel_code: string; room: string; lastDate: string; scores: Record<SourceKey, number[]>};
  const groups = new Map<string, Group>();
  let invalid = 0;
  for (const item of items) {
    const room = (item.room || '').trim();
    const key = sourceKey(item.source);
    // Con un tag scelto vale il voto di quel tag, altrimenti il voto generale.
    const value = category ? (item.scores?.[category] ?? null) : item.rating;
    if (!room || !key || value === null || !Number.isFinite(value)) continue;
    const scale = SOURCES.find(s => s.key === key)!.scale;
    if (value < 0 || value > scale) { invalid += 1; continue; }
    const id = `${item.hotel_code}:${room}`;
    const group: Group = groups.get(id) || {hotel: item.hotel, hotel_code: item.hotel_code, room, lastDate: '', scores: {Booking: [], Google: [], TripAdvisor: []}};
    group.scores[key].push(value);
    if (item.date > group.lastDate) group.lastDate = item.date;
    groups.set(id, group);
  }
  const rows = [...groups.values()].map(group => {
    const bySource = {} as Record<SourceKey, SourceAverage | null>;
    let total = 0;
    for (const {key} of SOURCES) {
      const scores = group.scores[key];
      total += scores.length;
      bySource[key] = scores.length
        ? {average: round2(scores.reduce((sum, value) => sum + value, 0) / scores.length), count: scores.length, min: Math.min(...scores), max: Math.max(...scores)}
        : null;
    }
    return {hotel: group.hotel, hotel_code: group.hotel_code, room: group.room, lastDate: group.lastDate, total, bySource};
  });
  return {rows, invalid};
}

/** Media generale per fonte su tutte le camere, pesata sul numero di voti. */
export function sourceOverview(rows: RoomAverage[]): Record<SourceKey, SourceAverage | null> {
  const result = {} as Record<SourceKey, SourceAverage | null>;
  for (const {key} of SOURCES) {
    let count = 0, sum = 0, min = Infinity, max = -Infinity;
    for (const row of rows) {
      const entry = row.bySource[key];
      if (!entry) continue;
      count += entry.count; sum += entry.average * entry.count;
      min = Math.min(min, entry.min); max = Math.max(max, entry.max);
    }
    result[key] = count ? {average: round2(sum / count), count, min, max} : null;
  }
  return result;
}
