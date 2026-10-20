import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesRoomGroup, roomGroupKey} from '../src/lib/roomGroups.ts';

test('assegna le camere al piano giusto', () => {
  assert.equal(roomGroupKey('gio', '126'), 'cantine-1');
  assert.equal(roomGroupKey('gio', '225'), 'cantine-2');
  assert.equal(roomGroupKey('gio', '233'), 'cantine-2');
  assert.equal(roomGroupKey('gio', '332'), 'cantine-3');
  assert.equal(roomGroupKey('gio', '434'), 'cantine-4');
});

test('camere fuori elenco, altri hotel e senza camera vanno in altre', () => {
  assert.equal(roomGroupKey('gio', '4407'), 'other');
  assert.equal(roomGroupKey('gio', null), 'other');
  assert.equal(roomGroupKey('choco', '126'), 'other');
});

test('filtro: tutte, tutte le cantine, singolo piano', () => {
  assert.equal(matchesRoomGroup('all', 'gio', null), true);
  assert.equal(matchesRoomGroup('cantine', 'gio', '227'), true);
  assert.equal(matchesRoomGroup('cantine', 'gio', '4407'), false);
  assert.equal(matchesRoomGroup('cantine-3', 'gio', '326'), true);
  assert.equal(matchesRoomGroup('cantine-3', 'gio', '426'), false);
});

test('moquette: solo le 8 camere indicate, solo Hotel Giò', async () => {
  const {hasMoquette, matchesFloor} = await import('../src/lib/roomGroups.ts');
  for (const r of ['125', '211', '218', '221', '224', '312', '323', '412']) assert.equal(hasMoquette('gio', r), true);
  assert.equal(hasMoquette('gio', '126'), false);
  assert.equal(hasMoquette('choco', '125'), false);
  assert.equal(matchesFloor('moquette', 'gio', '221'), true);
  assert.equal(matchesFloor('moquette', 'gio', '222'), false);
  assert.equal(matchesFloor('no-moquette', 'gio', '222'), true);
  assert.equal(matchesFloor('no-moquette', 'gio', null), false);
  assert.equal(matchesFloor('all', 'gio', null), true);
});
