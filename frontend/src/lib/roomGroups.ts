// Gruppi camere dell'Hotel Giò (filtro "Zona"). Le camere non elencate finiscono in "altre".
const range = (from: number, to: number) => Array.from({length: to - from + 1}, (_, i) => String(from + i));

export const GIO_ROOM_GROUPS = [
  {key: 'cantine-1', label: '1 Cantine Wine', rooms: range(126, 131)},
  {key: 'cantine-2', label: '2 Cantine Wine', rooms: range(225, 233)},
  {key: 'cantine-3', label: '3 Cantine Wine', rooms: range(326, 332)},
  {key: 'cantine-4', label: '4 Cantine Wine', rooms: range(426, 434)},
] as const;

// Mappa ricavata dal file housekeeping di Hotel Giò: tre cifre = Wine,
// quattro cifre = Jazz. I buchi riflettono camere non presenti nel file.
export const GIO_WINE_ROOMS = [
  ...range(101, 117), ...range(119, 131),
  ...range(201, 214), ...range(216, 233),
  ...range(301, 315), ...range(317, 332),
  ...range(401, 415), ...range(417, 434),
] as const;

export const GIO_JAZZ_ROOMS = [
  ...range(1101, 1112), '1114', '1115', '1116', '1118', '1119', '1120', '1121',
  ...range(2201, 2212), '2214', '2215', '2216', '2218', '2219', '2220', '2221',
  ...range(3301, 3312), '3314', '3315', '3316', '3318', '3319', '3320', '3321',
  ...range(4401, 4412), '4414', '4415', '4416', '4418', '4419', '4420', '4421',
] as const;

export type RoomBrand = 'Jazz' | 'Wine';
export type RoomGroupKey = 'all' | 'jazz' | 'wine' | 'cantine' | 'other' | typeof GIO_ROOM_GROUPS[number]['key'];

export function roomBrand(hotelCode: string, room: string | null | undefined): RoomBrand | null {
  if (hotelCode !== 'gio') return null;
  const clean = (room || '').trim();
  if ((GIO_JAZZ_ROOMS as readonly string[]).includes(clean)) return 'Jazz';
  if ((GIO_WINE_ROOMS as readonly string[]).includes(clean)) return 'Wine';
  return null;
}

export function roomGroupKey(hotelCode: string, room: string | null | undefined): RoomGroupKey {
  if (hotelCode !== 'gio') return 'other';
  const clean = (room || '').trim();
  return GIO_ROOM_GROUPS.find(g => (g.rooms as readonly string[]).includes(clean))?.key ?? (roomBrand(hotelCode, clean)?.toLowerCase() as RoomGroupKey | undefined) ?? 'other';
}

export function matchesRoomGroup(filter: RoomGroupKey, hotelCode: string, room: string | null | undefined): boolean {
  if (filter === 'all') return true;
  if (filter === 'cantine') {
    const clean = (room || '').trim();
    return hotelCode === 'gio' && GIO_ROOM_GROUPS.some(g => (g.rooms as readonly string[]).includes(clean));
  }
  if (filter === 'jazz' || filter === 'wine') return roomBrand(hotelCode, room)?.toLowerCase() === filter;
  return roomGroupKey(hotelCode, room) === filter;
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
