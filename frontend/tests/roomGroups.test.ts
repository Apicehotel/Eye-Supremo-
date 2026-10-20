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
