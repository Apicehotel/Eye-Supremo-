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

// Tipologie ricavate dal file housekeeping di Hotel Giò. La zona (Wine/Jazz)
// resta separata dal tipo letto/capienza mostrato nella tabella.
const GIO_ROOM_TYPES = [
  {label: 'Matrimoniale Economy', rooms: ['121', '122', '217', '219', '220', '222', '319', '320', '418', '420', '421', '423']},
  {label: 'Matrimoniale Standard', rooms: ['102', '103', '104', '105', '106', '107', '109', '113', '114', '117', '119', '124', '202', '203', '204', '205', '209', '210', '213', '214', '216', '223', '301', '302', '303', '304', '306', '309', '310', '311', '314', '317', '322', '401', '402', '404', '406', '408', '409', '410', '411', '414', '417', '424']},
  {label: 'Matrimoniale Superior', rooms: ['111', '112', '126', '127', '128', '129', '130', '131', '225', '226', '229', '230', '232', '233', '324', '325', '328', '329', '330', '331', '332', '426', '427', '428', '430', '431', '432', '433', '434', '1101', '1103', '1104', '1105', '1106', '1107', '1108', '1109', '1110', '1111', '1112', '1114', '1115', '1116', '1118', '1119', '1121', '2201', '2203', '2204', '2205', '2206', '2207', '2208', '2209', '2210', '2211', '2212', '2214', '2215', '2216', '2218', '2219', '2221', '3301', '3303', '3304', '3305', '3306', '3307', '3308', '3309', '3310', '3311', '3314', '3315', '3318', '3319', '3321', '4401', '4403', '4404', '4405', '4406', '4407', '4408', '4409', '4410', '4411', '4414', '4415', '4416', '4418', '4419', '4421']},
  {label: 'Quadrupla', rooms: ['116', '120', '123', '206', '318', '321']},
  {label: 'Singola', rooms: ['125', '211', '218', '221', '224', '312', '323', '412', '419', '422', '425']},
  {label: 'Suite', rooms: ['1102', '2202', '3302', '4402']},
  {label: 'Tripla Standard', rooms: ['101', '108', '110', '115', '201', '207', '208', '212', '305', '307', '308', '313', '315', '403', '405', '407', '413', '415']},
  {label: 'Tripla Superior', rooms: ['227', '228', '231', '326', '327', '429', '1120', '2220', '3312', '3316', '3320', '4412', '4420']},
] as const;

export type RoomType = typeof GIO_ROOM_TYPES[number]['label'];

export function roomType(hotelCode: string, room: string | null | undefined): RoomType | null {
  if (hotelCode !== 'gio') return null;
  const clean = (room || '').trim();
  return GIO_ROOM_TYPES.find(type => (type.rooms as readonly string[]).includes(clean))?.label ?? null;
}

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
