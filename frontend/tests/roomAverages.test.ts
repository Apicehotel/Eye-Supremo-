import test from 'node:test';
import assert from 'node:assert/strict';
import {roomAverages, roomStatus, sourceKey, sourceOverview} from '../src/lib/roomAverages.ts';

const base = {hotel: 'Hotel Giò', hotel_code: 'gio'};

test('separa le medie per fonte senza mescolare le scale', () => {
  const {rows, invalid} = roomAverages([
    {...base, room: '2215', source: 'Booking', date: '2026-07-03', rating: 9},
    {...base, room: '2215', source: 'Booking', date: '2026-10-05', rating: 5},
    {...base, room: '2215', source: 'Google', date: '2026-09-01', rating: 4},
    {...base, room: '2215', source: 'TripAdvisor', date: '2026-08-01', rating: 5},
  ]);
  assert.equal(invalid, 0);
  assert.equal(rows.length, 1);
  assert.deepEqual(rows[0].bySource.Booking, {average: 7, count: 2, min: 5, max: 9});
  assert.deepEqual(rows[0].bySource.Google, {average: 4, count: 1, min: 4, max: 4});
  assert.deepEqual(rows[0].bySource.TripAdvisor, {average: 5, count: 1, min: 5, max: 5});
  assert.equal(rows[0].total, 4);
  assert.equal(rows[0].lastDate, '2026-10-05');
});

test('ignora voti fuori scala, senza camera o senza voto e li conta', () => {
  const {rows, invalid} = roomAverages([
    {...base, room: '4407', source: 'Booking', date: '2024-10-28', rating: 26},
    {...base, room: '4407', source: 'Booking', date: '2025-01-24', rating: 9},
    {...base, room: '4407', source: 'Google', date: '2025-01-25', rating: 7},
    {...base, room: null, source: 'Booking', date: '2025-01-24', rating: 8},
    {...base, room: '4407', source: 'Booking', date: '2025-02-01', rating: null},
    {...base, room: '4407', source: 'TXT', date: '2025-02-02', rating: 8},
  ]);
  assert.equal(invalid, 2);
  assert.equal(rows[0].bySource.Booking?.average, 9);
  assert.equal(rows[0].bySource.Booking?.count, 1);
  assert.equal(rows[0].bySource.Google, null);
});

test('la stessa camera in hotel diversi resta separata', () => {
  const {rows} = roomAverages([
    {...base, room: '101', source: 'Booking', date: '2026-01-01', rating: 8},
    {hotel: 'Chocohotel', hotel_code: 'choco', room: '101', source: 'Booking', date: '2026-01-02', rating: 6},
  ]);
  assert.equal(rows.length, 2);
});

test('media per fonte su tutte le camere pesata sui voti', () => {
  const {rows} = roomAverages([
    {...base, room: '101', source: 'Booking', date: '2026-01-01', rating: 10},
    {...base, room: '101', source: 'Booking', date: '2026-01-02', rating: 8},
    {...base, room: '202', source: 'Booking', date: '2026-01-03', rating: 6},
  ]);
  assert.equal(sourceOverview(rows).Booking?.average, 8);
  assert.equal(sourceOverview(rows).Google, null);
});

test('ignora camera 10 inventata da Vista dalla camera (voto Booking)', () => {
  const {rows, invalid} = roomAverages([
    {...base, room: '10', source: 'Booking', date: '2026-07-15', rating: 9},
    {...base, room: '10', source: 'Booking', date: '2026-07-16', rating: 9},
    {...base, room: '4411', source: 'Booking', date: '2026-07-17', rating: 8},
  ]);
  assert.equal(invalid, 2);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].room, '4411');
});

test('riconosce le fonti e valuta lo stato sulla scala giusta', () => {
  assert.equal(sourceKey(' booking.com '), 'Booking');
  assert.equal(sourceKey('tripadvisor'), 'TripAdvisor');
  assert.equal(sourceKey('TXT'), null);
  assert.equal(roomStatus(5.9, 10), 'attenzione');
  assert.equal(roomStatus(3, 5), 'monitorare');
  assert.equal(roomStatus(2.9, 5), 'attenzione');
  assert.equal(roomStatus(4, 5), 'ok');
});

test('voti per tag: la media usa il voto del tag scelto, separata per fonte', async () => {
  const {roomAverages, scoreCategories} = await import('../src/lib/roomAverages.ts');
  const base = {hotel: 'Hotel Giò', hotel_code: 'gio', room: '330', date: '2026-01-01'};
  const items = [
    {...base, source: 'Booking', rating: 8, scores: {Staff: 10, Colazione: 6}},
    {...base, source: 'Booking', rating: 9, scores: {Staff: 8}},
    {...base, source: 'TripAdvisor', rating: 4, scores: {Staff: 5, Posizione: 4}},
    {...base, source: 'Booking', rating: 7, scores: {Staff: 12}},
  ];
  assert.deepEqual(scoreCategories(items), ['Colazione', 'Posizione', 'Staff']);
  const staff = roomAverages(items, 'Staff');
  assert.equal(staff.rows[0].bySource.Booking?.average, 9);
  assert.equal(staff.rows[0].bySource.Booking?.count, 2);
  assert.equal(staff.rows[0].bySource.TripAdvisor?.average, 5);
  assert.equal(staff.invalid, 1);
  const colazione = roomAverages(items, 'Colazione');
  assert.equal(colazione.rows[0].bySource.Booking?.average, 6);
  assert.equal(colazione.rows[0].bySource.TripAdvisor, null);
  assert.equal(roomAverages(items).rows[0].bySource.Booking?.average, 8);
});

test('le parole non sono camere: «pulita», «super» vengono ignorate', async () => {
  const {roomAverages} = await import('../src/lib/roomAverages.ts');
  const base = {hotel: 'Hotel Giò', hotel_code: 'gio', date: '2026-01-01', source: 'Google', rating: 5};
  const result = roomAverages([{...base, room: 'pulita'}, {...base, room: 'super'}, {...base, room: '330'}]);
  assert.deepEqual(result.rows.map(r => r.room), ['330']);
});
