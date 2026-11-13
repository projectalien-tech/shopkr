/**
 * ShopKR study logger — Google Apps Script web app (v6.3.0)
 *
 * Receives batches of events from shopkr-study.html and writes them to two tabs
 * in the spreadsheet this script is bound to:
 *   events   — one row per interaction event
 *   sessions — one row per participant session (updated on every request)
 *
 * Setup: Extensions → Apps Script, paste this file, Deploy → New deployment →
 * Web app, Execute as "Me", Who has access "Anyone". Copy the /exec URL into
 * CONFIG.ENDPOINT_URL in shopkr-study.html. Full steps in the setup guide.
 * Updating from an earlier version: Deploy → Manage deployments → Edit →
 * Version: New version → Deploy (the URL stays the same).
 *
 * Duplicates: every event carries a per-session sequence number (seq). The highest
 * seq stored for each session is kept in Script Properties, and any event at or
 * below it is ignored, so retries and page-hide beacons never create duplicate rows.
 *
 * Withdrawals: once a session is withdrawn, the server stores nothing more for it
 * except its withdrawal marker, and its sessions row keeps only the ID and the flag.
 * Run purgeWithdrawn() to delete the events it sent before withdrawing.
 *
 * Condition assignment (action 'assign'): for links without ?cond=, the app asks for a cell
 * right after consent. The cell with the fewest ACTIVE participants is chosen (ties at random),
 * so groups stay balanced across all devices. Active = finished the task, or assigned less than
 * ASSIGN_RESERVATION_MIN minutes ago and not yet finished. Withdrawn participants free their slot.
 * The same session always gets the same cell back. Every assignment is listed in the
 * 'assignments' tab. To change the reservation time without editing code, add a Script property
 * (Project Settings → Script properties) named assign_reservation_min.
 */

const EVENTS_SHEET = 'events';
const SESSIONS_SHEET = 'sessions';
const EVENT_COLS = ['receivedAt', 'eventId', 'sessionId', 'pid', 'cond', 'appVersion', 'seq', 'clientTime',
  'elapsedMs', 'phase', 'screen', 'type', 'pattern', 'detail'];
const SESSION_COLS = ['sessionId', 'pid', 'condAssigned', 'condFinal', 'assignedBy', 'appVersion', 'lang',
  'consentAt', 'taskStartAt', 'taskEndAt', 'taskEndReason', 'taskDurationMs', 'orderCount', 'lastOrderTotal',
  'overBudget', 'protectionKept', 'trialKept', 'membershipActive', 'marketingEmail', 'patternsOn', 'patternsSeen',
  'phase', 'withdrawn', 'completionCode', 'userAgent', 'lastSeq', 'firstSeen', 'lastUpdate',
  'design', 'factorA', 'factorB',
  'membershipFees', 'totalSpent', 'joinedVia', 'nagShown', 'nagDeclines', 'nagEscaped', 'gatePrompts',
  'memberBenefit', 'joinedAgainstInterest'];   // new columns are only ever added at the end
const W_COL = SESSION_COLS.indexOf('withdrawn');
const ASSIGN_SHEET = 'assignments';
const ASSIGN_COLS = ['sessionId', 'design', 'cell', 'assignedBy', 'assignedAt', 'status', 'updatedAt'];
const A_CELL = 2, A_BY = 3, A_AT = 4, A_STATUS = 5;
const ASSIGN_RESERVATION_MIN = 60;
const MAX_EVENTS_PER_REQUEST = 500;

/** Health check: open the /exec URL in a browser (or the app's "Test server" button). */
function doGet(e) {
  return json_({ok: true, service: 'shopkr-logger', version: '6.3.0', time: new Date().toISOString()});
}

function doPost(e) {
  const lock = LockService.getScriptLock();
  try {
    lock.waitLock(25000);   // serialise writes so concurrent participants never overwrite each other
    const data = JSON.parse((e && e.postData && e.postData.contents) || '{}');
    const session = data.session || {};
    const sid = String(session.sessionId || data.sessionId || '');   // assign requests carry it at the top level
    if (!/^[0-9a-f-]{20,64}$/i.test(sid)) return json_({ok: false, error: 'missing or invalid sessionId'});

    const ss = SpreadsheetApp.getActiveSpreadsheet();
    if (data.action === 'assign') return json_(assign_(ss, sid, data));
    const ev = sheet_(ss, EVENTS_SHEET, EVENT_COLS);
    const se = sheet_(ss, SESSIONS_SHEET, SESSION_COLS);
    const found = findSession_(se, sid);
    // A withdrawal is never undone: the flag in this request or an earlier one both count.
    const withdrawn = !!data.withdraw || session.withdrawn === true || !!(found && found.values[W_COL] === true);

    const props = PropertiesService.getScriptProperties();
    const seqKey = 'seq_' + sid;
    let maxSeq = Number(props.getProperty(seqKey) || 0);
    const now = new Date();

    const fresh = (data.events || []).slice(0, MAX_EVENTS_PER_REQUEST)
      .filter(x => x && String(x.sessionId) === sid && Number(x.seq) > maxSeq)
      .sort((a, b) => Number(a.seq) - Number(b.seq));
    // For a withdrawn session only the withdrawal marker is stored; the rest is acknowledged and dropped.
    const keep = withdrawn ? fresh.filter(x => x.type === 'withdrawal') : fresh;
    const rows = keep.map(x => [now, x.eventId, x.sessionId, x.pid, x.cond, x.appVersion, Number(x.seq), x.ts,
      x.elapsedMs, x.phase, x.screen, x.type, x.pattern, x.detail].map(safe_));
    if (rows.length) ev.getRange(ev.getLastRow() + 1, 1, rows.length, EVENT_COLS.length).setValues(rows);
    if (fresh.length) {
      maxSeq = Math.max(maxSeq, Number(fresh[fresh.length - 1].seq));
      props.setProperty(seqKey, String(maxSeq));
    }
    upsertSession_(se, found, sid, session, maxSeq, withdrawn, now);
    // Keep the assignments tab true to what each participant actually saw: record cells assigned on the
    // device (server unreachable) or pinned by link, correct a cell the app never received, and track
    // finished / withdrawn participants, since all of these change the balance.
    if (!withdrawn) syncAssignment_(ss, sid, session, now);
    if (withdrawn) setAssignmentStatus_(ss, sid, 'withdrawn', now);
    else if (session.taskEndAt) setAssignmentStatus_(ss, sid, 'complete', now);
    return json_({ok: true, appended: rows.length, maxSeq: maxSeq});
  } catch (err) {
    return json_({ok: false, error: String(err && err.message || err)});
  } finally {
    try { lock.releaseLock(); } catch (e2) {}
  }
}

/** Choose a cell for a new session: fewest active participants, ties at random. Runs under the lock. */
function assign_(ss, sid, data) {
  const design = String(data.design || 'default').slice(0, 60);
  const cells = [...new Set((Array.isArray(data.cells) ? data.cells : []).map(String))]
    .filter(c => /^[A-Za-z0-9_-]{1,24}$/.test(c));
  if (cells.length < 2 || cells.length > 16) return {ok: false, error: 'cells must list 2 to 16 condition codes'};
  const sh = sheet_(ss, ASSIGN_SHEET, ASSIGN_COLS);
  const vals = sh.getDataRange().getValues();
  for (let r = 1; r < vals.length; r++) {
    if (String(vals[r][0]) === sid && String(vals[r][1]) === design && vals[r][A_STATUS] !== 'withdrawn') {
      return {ok: true, cell: String(vals[r][A_CELL]), reused: true};
    }
  }
  const now = new Date();
  const reserveMin = Number(PropertiesService.getScriptProperties().getProperty('assign_reservation_min')) || ASSIGN_RESERVATION_MIN;
  const cutoff = now.getTime() - reserveMin * 60000;
  const counts = {};
  cells.forEach(c => { counts[c] = 0; });
  for (let r = 1; r < vals.length; r++) {
    const cell = String(vals[r][A_CELL]), status = vals[r][A_STATUS];
    if (String(vals[r][1]) !== design || !(cell in counts)) continue;
    const at = vals[r][A_AT] instanceof Date ? vals[r][A_AT].getTime() : Date.parse(vals[r][A_AT]);
    if (status === 'complete' || (status === 'pending' && at >= cutoff)) counts[cell] += 1;
  }
  const min = Math.min.apply(null, cells.map(c => counts[c]));
  const choices = cells.filter(c => counts[c] === min);
  const cell = choices[Math.floor(Math.random() * choices.length)];
  sh.appendRow([sid, design, cell, 'server', now, 'pending', now].map(safe_));
  counts[cell] += 1;
  return {ok: true, cell: cell, counts: counts};
}

/** Make the assignments row match the cell the app reports it is using. */
function syncAssignment_(ss, sid, session, now) {
  const cell = session.condAssigned, design = session.design;
  if (!cell || !design || !/^[A-Za-z0-9_-]{1,24}$/.test(String(cell))) return;
  const sh = sheet_(ss, ASSIGN_SHEET, ASSIGN_COLS);
  const hit = sh.getLastRow() >= 2 ? sh.getRange(2, 1, sh.getLastRow() - 1, 1).createTextFinder(sid).matchEntireCell(true).findNext() : null;
  if (!hit) {
    sh.appendRow([sid, String(design), String(cell), String(session.assignedBy || ''), now, 'pending', now].map(safe_));
    return;
  }
  const row = sh.getRange(hit.getRow(), 1, 1, ASSIGN_COLS.length).getValues()[0];
  if (String(row[A_CELL]) !== String(cell)) {
    sh.getRange(hit.getRow(), A_CELL + 1, 1, 2).setValues([[String(cell), String(session.assignedBy || '')].map(safe_)]);
    sh.getRange(hit.getRow(), ASSIGN_COLS.length).setValues([[now]]);
  }
}

/** Mark a session's assignment complete or withdrawn (a withdrawal is never overwritten). */
function setAssignmentStatus_(ss, sid, status, now) {
  const sh = ss.getSheetByName(ASSIGN_SHEET);
  if (!sh || sh.getLastRow() < 2) return;
  const hit = sh.getRange(2, 1, sh.getLastRow() - 1, 1).createTextFinder(sid).matchEntireCell(true).findNext();
  if (!hit) return;
  const cur = sh.getRange(hit.getRow(), A_STATUS + 1).getValues()[0][0];
  if (cur === status || cur === 'withdrawn') return;
  sh.getRange(hit.getRow(), A_STATUS + 1, 1, 2).setValues([[status, now]]);
}

/** Find a session's row (below the header) by sessionId in column A. */
function findSession_(se, sid) {
  const last = se.getLastRow();
  if (last < 2) return null;
  const hit = se.getRange(2, 1, last - 1, 1).createTextFinder(sid).matchEntireCell(true).findNext();
  if (!hit) return null;
  const row = hit.getRow();
  return {row: row, values: se.getRange(row, 1, 1, SESSION_COLS.length).getValues()[0]};
}

/**
 * Insert or update the session's row. Fields missing from the request keep their stored
 * value, so a partial summary never blanks a row. A withdrawn session keeps only its ID,
 * the flag and bookkeeping columns.
 */
function upsertSession_(se, found, sid, session, maxSeq, withdrawn, now) {
  const prev = found ? found.values : null;
  const row = SESSION_COLS.map((c, i) => {
    if (c === 'sessionId') return sid;
    if (c === 'lastSeq') return maxSeq;
    if (c === 'firstSeen') return (prev && prev[i]) || now;
    if (c === 'lastUpdate') return now;
    if (c === 'withdrawn') return withdrawn;
    if (withdrawn) return '';
    const v = session[c];
    if (v === undefined) return prev ? prev[i] : '';
    return v;
  }).map(safe_);
  if (found) se.getRange(found.row, 1, 1, SESSION_COLS.length).setValues([row]);
  else se.appendRow(row);
}

/**
 * Run this manually (Apps Script editor → select purgeWithdrawn → Run) to delete
 * every event row of sessions whose participant withdrew. Their sessions row is
 * kept, with withdrawn = TRUE and all outcome columns cleared, as an audit trail.
 * It takes the same lock as doPost, so it is safe to run while participants are active.
 */
function purgeWithdrawn() {
  const lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    const ss = SpreadsheetApp.getActiveSpreadsheet();
    const se = sheet_(ss, SESSIONS_SHEET, SESSION_COLS);
    const ev = sheet_(ss, EVENTS_SHEET, EVENT_COLS);
    const sVals = se.getDataRange().getValues();
    const ids = new Set();
    const keepCols = ['sessionId', 'withdrawn', 'lastSeq', 'firstSeen', 'lastUpdate'];
    for (let r = 1; r < sVals.length; r++) {
      if (sVals[r][W_COL] === true) {
        ids.add(String(sVals[r][0]));
        const cleared = SESSION_COLS.map((c, i) => keepCols.indexOf(c) >= 0 ? sVals[r][i] : '').map(safe_);
        se.getRange(r + 1, 1, 1, SESSION_COLS.length).setValues([cleared]);
      }
    }
    if (!ids.size) { Logger.log('No withdrawn sessions.'); return; }
    const eVals = ev.getDataRange().getValues();
    const sidCol = EVENT_COLS.indexOf('sessionId');
    // Values read back from Sheets lose the protective apostrophe, so re-apply safe_ before rewriting.
    const kept = eVals.filter((row, i) => i === 0 || !ids.has(String(row[sidCol])))
      .map((row, i) => i === 0 ? row : row.map(safe_));
    const removed = eVals.length - kept.length;
    ev.clearContents();
    ev.getRange(1, 1, kept.length, EVENT_COLS.length).setValues(kept);
    Logger.log('Removed ' + removed + ' event rows from ' + ids.size + ' withdrawn session(s).');
  } finally {
    lock.releaseLock();
  }
}

/** Get a tab, creating it with a frozen bold header row if it does not exist yet. */
function sheet_(ss, name, cols) {
  let sh = ss.getSheetByName(name);
  if (!sh) {
    sh = ss.insertSheet(name);
    sh.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
    sh.setFrozenRows(1);
    return sh;
  }
  // A tab created by an earlier version gets the newer columns added to its header.
  const head = sh.getRange(1, 1, 1, cols.length).getValues()[0];
  if (cols.some((c, i) => head[i] !== c)) sh.getRange(1, 1, 1, cols.length).setValues([cols]).setFontWeight('bold');
  return sh;
}

/** Neutralise spreadsheet formulas in text (a value starting with = + - @ would run as a formula). */
function safe_(v) {
  if (v === null || v === undefined) return '';
  if (typeof v === 'number' || typeof v === 'boolean' || v instanceof Date) return v;
  const s = String(v);
  return /^[=+\-@\t\r]/.test(s) ? "'" + s : s;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
