/*
 * Eye Supremo → Recensioni Gio
 *
 * Deploy as a Google Apps Script Web App (execute as the sheet owner).
 * Store EYE_REVIEW_SHEET_SECRET in Script Properties.  The endpoint receives
 * one review event and merges it into the existing row for its room.
 */
const SPREADSHEET_ID = '12OwJPLIMaOr3uDkq_zLqPozDxTpOwlAskhx5bIqftWs';
const HEADERS = ['Camera', 'Difetti rilevati', 'N. segnalazioni', 'Ultima segnalazione', 'Fonte', 'Voto', 'Recensione', 'Aggiornato il'];
const SYNC_KEYS_COLUMN = 9; // hidden helper column I

function doPost(e) {
  const payload = JSON.parse((e.postData && e.postData.contents) || '{}');
  const expected = PropertiesService.getScriptProperties().getProperty('EYE_REVIEW_SHEET_SECRET');
  if (!expected || payload.secret !== expected) return json_({ok: false, error: 'unauthorized'}, 401);
  const event = payload.event || {};
  if (!event.event_id || !event.sheet || !event.room || !Array.isArray(event.defects) || !event.defects.length) {
    return json_({ok: false, error: 'invalid_event'}, 400);
  }

  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const sheet = SpreadsheetApp.openById(SPREADSHEET_ID).getSheetByName(event.sheet);
    if (!sheet) return json_({ok: false, error: 'sheet_not_found'}, 404);
    ensureHeaders_(sheet);
    const row = roomRow_(sheet, String(event.room));
    const values = sheet.getRange(row, 1, 1, SYNC_KEYS_COLUMN).getValues()[0];
    const keys = parseKeys_(values[SYNC_KEYS_COLUMN - 1]);
    if (keys.indexOf(event.event_id) !== -1) return json_({ok: true, duplicate: true, row: row});

    const defects = unique_(splitLines_(values[1]).concat(event.defects));
    const count = Number(values[2] || 0) + 1;
    const newest = newerDate_(values[3], event.review_date);
    const sources = unique_(splitLines_(values[4]).concat(event.source || []));
    const excerpts = splitBlocks_(values[6]);
    excerpts.push(formatReview_(event));
    keys.push(event.event_id);

    sheet.getRange(row, 1, 1, SYNC_KEYS_COLUMN).setValues([[
      values[0] || String(event.room), defects.join('\n'), count, newest,
      sources.join('\n'), event.rating === null || event.rating === undefined ? values[5] : event.rating,
      unique_(excerpts).join('\n\n'), new Date(), JSON.stringify(keys)
    ]]);
    sheet.getRange(row, 1, 1, 8).setWrap(true);
    sheet.hideColumns(SYNC_KEYS_COLUMN);
    return json_({ok: true, duplicate: false, row: row, added_defects: defects.length});
  } finally {
    lock.releaseLock();
  }
}

function ensureHeaders_(sheet) {
  if (sheet.getRange(1, 1).getValue() !== 'Camera') sheet.getRange(1, 1, 1, 8).setValues([HEADERS]);
  sheet.getRange(1, SYNC_KEYS_COLUMN).setValue('Chiavi sincronizzazione');
}

function roomRow_(sheet, room) {
  const last = Math.max(2, sheet.getLastRow());
  const values = sheet.getRange(2, 1, last - 1, 1).getDisplayValues();
  for (let index = 0; index < values.length; index++) if (values[index][0] === room) return index + 2;
  const row = last + 1;
  sheet.getRange(row, 1).setValue(room);
  return row;
}

function parseKeys_(value) { try { return Array.isArray(JSON.parse(value || '[]')) ? JSON.parse(value || '[]') : []; } catch (_) { return []; } }
function splitLines_(value) { return String(value || '').split(/\n+/).map(x => x.trim()).filter(Boolean); }
function splitBlocks_(value) { return String(value || '').split(/\n\s*\n/).map(x => x.trim()).filter(Boolean); }
function unique_(items) { const seen = {}; return items.filter(item => { const text = String(item || '').trim(); const key = text.toLocaleLowerCase('it'); if (!text || seen[key]) return false; seen[key] = true; return true; }); }
function newerDate_(current, incoming) { const existing = current instanceof Date ? current : new Date(current || 0); const next = new Date(incoming); return isNaN(next) || existing > next ? current : incoming; }
function formatReview_(event) { return [event.review_date, event.source, event.rating === null || event.rating === undefined ? '' : event.rating].filter(Boolean).join(' · ') + '\n' + String(event.text || '').trim(); }
function json_(body, status) { return ContentService.createTextOutput(JSON.stringify(Object.assign({status: status}, body))).setMimeType(ContentService.MimeType.JSON); }
