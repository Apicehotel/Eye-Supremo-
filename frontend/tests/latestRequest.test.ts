import test from 'node:test';
import assert from 'node:assert/strict';
import {LatestRequest} from '../src/lib/latestRequest.ts';

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (error: Error) => void;
  const promise = new Promise<T>((yes, no) => {resolve = yes; reject = no;});
  return {promise, resolve, reject};
}

test('una risposta vecchia non sostituisce la ricerca più recente', async () => {
  const requests = new LatestRequest();
  const first = deferred<string>();
  const second = deferred<string>();
  let visible = '';
  const old = requests.start();
  const oldWork = first.promise.then(value => {if (old.current()) visible = value;});
  const latest = requests.start();
  const newWork = second.promise.then(value => {if (latest.current()) visible = value;});
  assert.equal(old.signal.aborted, true);
  second.resolve('ricerca nuova'); await newWork;
  first.resolve('risposta tardiva'); await oldWork;
  assert.equal(visible, 'ricerca nuova');
});

test('un errore tardivo non cancella un risultato valido', async () => {
  const requests = new LatestRequest();
  const first = deferred<string>();
  let visible = 'risultato valido';
  const old = requests.start();
  const work = first.promise.catch(() => {if (old.current()) visible = '';});
  requests.start(); first.reject(new Error('errore vecchio')); await work;
  assert.equal(visible, 'risultato valido');
});

test('uscire dalla pagina annulla la richiesta e ignora risposte successive', async () => {
  const requests = new LatestRequest();
  const pending = deferred<string>();
  let updated = false;
  const work = requests.start();
  const result = pending.promise.then(() => {if (work.current()) updated = true;});
  requests.cancel(); pending.resolve('risposta'); await result;
  assert.equal(work.signal.aborted, true);
  assert.equal(updated, false);
});
