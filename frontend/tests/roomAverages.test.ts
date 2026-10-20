import test from 'node:test';
import assert from 'node:assert/strict';
import {roomAverages, roomStatus} from '../src/lib/roomAverages.ts';

const base = {hotel: 'Hotel Giò', hotel_code: 'gio'};

test('calcola la media per camera e ignora recensioni senza camera o senza voto', () => {
  const rows = roomAverages([
    {...base, room: '2215', source: 'Booking', date: '2026-07-03', score: 9},
    {...base, room: '2215', source: 'Booking', date: '2026-10-05', score: 5},
    {...base, room: '2215', source: 'Google', date: '2026-09-01', score: 8},
    {...base, room: null, source: 'Booking', date: '2026-09-01', score: 3},
    {...base, room: '310', source: 'Booking', date: '2026-09-01', score: null},
  ]);
  assert.equal(rows.length, 1);
  assert.equal(rows[0].room, '2215');
  assert.equal(rows[0].reviews, 3);
  assert.equal(rows[0].average, 7.33);
  assert.equal(rows[0].min, 5);
  assert.equal(rows[0].max, 9);
  assert.equal(rows[0].lastDate, '2026-10-05');
  assert.deepEqual(rows[0].sources, [{source: 'Booking', count: 2}, {source: 'Google', count: 1}]);
});

test('la stessa camera in hotel diversi resta separata', () => {
  const rows = roomAverages([
    {...base, room: '101', source: 'Booking', date: '2026-01-01', score: 8},
    {hotel: 'Chocohotel', hotel_code: 'choco', room: '101', source: 'Booking', date: '2026-01-02', score: 6},
  ]);
  assert.equal(rows.length, 2);
});

test('stato camera: attenzione sotto 6, monitorare sotto 7,5', () => {
  assert.equal(roomStatus(5.99), 'attenzione');
  assert.equal(roomStatus(6), 'monitorare');
  assert.equal(roomStatus(7.49), 'monitorare');
  assert.equal(roomStatus(7.5), 'ok');
});
