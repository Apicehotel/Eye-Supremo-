// Gruppi camere dell'Hotel Giò (filtro "Zona"). Le camere non elencate finiscono in "altre".
const range = (from: number, to: number) => Array.from({length: to - from + 1}, (_, i) => String(from + i));

export const GIO_ROOM_GROUPS = [
  {key: 'cantine-1', label: '1 Cantine Wine', rooms: range(126, 131)},
  {key: 'cantine-2', label: '2 Cantine Wine', rooms: range(225, 233)},
  {key: 'cantine-3', label: '3 Cantine Wine', rooms: range(326, 332)},
  {key: 'cantine-4', label: '4 Cantine Wine', rooms: range(426, 434)},
] as const;

export type RoomGroupKey = 'all' | 'cantine' | 'other' | typeof GIO_ROOM_GROUPS[number]['key'];

export function roomGroupKey(hotelCode: string, room: string | null | undefined): RoomGroupKey {
  if (hotelCode !== 'gio') return 'other';
  const clean = (room || '').trim();
  return GIO_ROOM_GROUPS.find(g => (g.rooms as readonly string[]).includes(clean))?.key ?? 'other';
}

export function matchesRoomGroup(filter: RoomGroupKey, hotelCode: string, room: string | null | undefined): boolean {
  if (filter === 'all') return true;
  const key = roomGroupKey(hotelCode, room);
  return filter === 'cantine' ? key !== 'other' : key === filter;
}

// Camere con moquette dell'Hotel Giò (filtro "Pavimento", indipendente dalla zona).
export const GIO_MOQUETTE_ROOMS = ['125', '211', '218', '221', '224', '312', '323', '412'] as const;

export type FloorFilter = 'all' | 'moquette' | 'no-moquette';

export function hasMoquette(hotelCode: string, room: string | null | undefined): boolean {
  return hotelCode === 'gio' && (GIO_MOQUETTE_ROOMS as readonly string[]).includes((room || '').trim());
}

export function matchesFloor(filter: FloorFilter, hotelCode: string, room: string | null | undefined): boolean {
  if (filter === 'all') return true;
  if (!(room || '').trim()) return false;
  return (filter === 'moquette') === hasMoquette(hotelCode, room);
}
