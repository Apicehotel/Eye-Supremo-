export type RoomScoreInput = {
  hotel: string;
  hotel_code: string;
  room: string | null;
  source: string | null;
  date: string;
  /** Voto già normalizzato su scala 10 (null = senza voto). */
  score: number | null;
};

export type RoomAverage = {
  hotel: string;
  hotel_code: string;
  room: string;
  reviews: number;
  average: number;
  min: number;
  max: number;
  lastDate: string;
  sources: {source: string; count: number}[];
};

export type RoomStatus = 'ok' | 'monitorare' | 'attenzione';

export function roomStatus(average: number): RoomStatus {
  return average < 6 ? 'attenzione' : average < 7.5 ? 'monitorare' : 'ok';
}

/** Media dei voti per camera: contano solo recensioni con camera e voto. */
export function roomAverages(items: RoomScoreInput[]): RoomAverage[] {
  type Group = {hotel: string; hotel_code: string; room: string; scores: number[]; lastDate: string; sources: Map<string, number>};
  const groups = new Map<string, Group>();
  for (const item of items) {
    const room = (item.room || '').trim();
    if (!room || item.score === null || !Number.isFinite(item.score)) continue;
    const key = `${item.hotel_code}:${room}`;
    const group: Group = groups.get(key) || {hotel: item.hotel, hotel_code: item.hotel_code, room, scores: [], lastDate: '', sources: new Map()};
    group.scores.push(item.score);
    if (item.date > group.lastDate) group.lastDate = item.date;
    const source = item.source || 'Fonte non indicata';
    group.sources.set(source, (group.sources.get(source) || 0) + 1);
    groups.set(key, group);
  }
  return [...groups.values()].map(group => ({
    hotel: group.hotel,
    hotel_code: group.hotel_code,
    room: group.room,
    reviews: group.scores.length,
    average: Math.round(group.scores.reduce((sum, value) => sum + value, 0) / group.scores.length * 100) / 100,
    min: Math.min(...group.scores),
    max: Math.max(...group.scores),
    lastDate: group.lastDate,
    sources: [...group.sources.entries()].map(([source, count]) => ({source, count})).sort((a, b) => b.count - a.count || a.source.localeCompare(b.source)),
  }));
}
