import test from 'node:test';
import assert from 'node:assert/strict';
import {matchesRoomGroup, roomBrand, roomGroupKey, roomType} from '../src/lib/roomGroups.ts';

test('assegna le camere al piano giusto', () => {
  assert.equal(roomGroupKey('gio', '126'), 'cantine-1');
  assert.equal(roomGroupKey('gio', '225'), 'cantine-2');
  assert.equal(roomGroupKey('gio', '233'), 'cantine-2');
  assert.equal(roomGroupKey('gio', '332'), 'cantine-3');
  assert.equal(roomGroupKey('gio', '434'), 'cantine-4');
});

test('assegna il brand Jazz/Wine senza contaminare gli altri hotel', () => {
  assert.equal(roomBrand('gio', '4407'), 'Jazz');
  assert.equal(roomBrand('gio', '126'), 'Wine');
  assert.equal(roomBrand('choco', '101'), null);
  assert.equal(roomGroupKey('gio', '9999'), 'other');
  assert.equal(roomGroupKey('gio', null), 'other');
  assert.equal(roomGroupKey('choco', '126'), 'other');
});

test('assegna il tag della tipologia camera dal file housekeeping', () => {
  assert.equal(roomType('gio', '101'), 'Tripla Standard');
  assert.equal(roomType('gio', '125'), 'Singola');
  assert.equal(roomType('gio', '111'), 'Matrimoniale Superior');
  assert.equal(roomType('gio', '1102'), 'Suite');
  assert.equal(roomType('gio', '429'), 'Tripla Superior');
  assert.equal(roomType('choco', '101'), null);
  assert.equal(roomType('gio', '9999'), null);
});

test('filtro: tutte, Jazz, Wine, cantine e singolo piano', () => {
  assert.equal(matchesRoomGroup('all', 'gio', null), true);
  assert.equal(matchesRoomGroup('jazz', 'gio', '4407'), true);
  assert.equal(matchesRoomGroup('jazz', 'gio', '126'), false);
  assert.equal(matchesRoomGroup('wine', 'gio', '126'), true);
  assert.equal(matchesRoomGroup('wine', 'gio', '4407'), false);
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
