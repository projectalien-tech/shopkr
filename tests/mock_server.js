// Runs the real Code.gs in Node with mocked Google services, served over HTTP like an
// Apps Script web app (CORS *). Mimics Sheets: a leading apostrophe marks text and is not
// returned by getValues; any string written that starts with '=' is recorded as a formula.
const fs = require('fs'), http = require('http'), vm = require('vm');
const code = fs.readFileSync(process.argv[3] || require('path').join(__dirname, '..', 'apps-script', 'Code.gs'), 'utf8');
const PORT = Number(process.argv[2] || 8765);
let offline = false, delayMs = 0;
const formulas = [];
const lockLog = [];   // 'acquire' / 'release' with the function that held it
let current = null;

function cellIn(v, where){
  if (typeof v === 'string' && v.startsWith('=')) formulas.push({where, v});
  return v;
}
function cellOut(v){ return (typeof v === 'string' && v.startsWith("'")) ? v.slice(1) : v; }
function makeSheet(name){
  const data = [];
  const sheet = {
    name, data,
    getLastRow: () => data.length,
    setFrozenRows(){},
    appendRow(row){ data.push(row.map(v => cellIn(v, name))); },
    clearContents(){ data.length = 0; },
    getDataRange(){ return sheet.getRange(1, 1, data.length || 1, Math.max(1, ...data.map(r => r.length))); },
    getRange(r, c, nr = 1, nc = 1){
      const range = {
        setValues(vals){ vals.forEach((row, i) => { const rr = r - 1 + i; while (data.length <= rr) data.push([]); row.forEach((v, j) => { data[rr][c - 1 + j] = cellIn(v, name); }); }); return range; },
        getValues(){ const out = []; for (let i = 0; i < nr; i++){ const row = []; for (let j = 0; j < nc; j++) row.push(cellOut((data[r - 1 + i] || [])[c - 1 + j] ?? '')); out.push(row); } return out; },
        setFontWeight(){ return range; },
        createTextFinder(text){ let exact = false; const f = { matchEntireCell(b){ exact = b; return f; }, findNext(){
          for (let i = 0; i < nr; i++){ const v = String(cellOut((data[r - 1 + i] || [])[c - 1] ?? '')); if (exact ? v === text : v.includes(text)) return {getRow: () => r + i}; } return null; } }; return f; },
      };
      return range;
    },
  };
  return sheet;
}
const sheets = {}, props = {};
const ctx = {
  SpreadsheetApp: {getActiveSpreadsheet: () => ({ getSheetByName: n => sheets[n] || null, insertSheet: n => (sheets[n] = makeSheet(n)) })},
  LockService: {getScriptLock: () => ({waitLock(){ lockLog.push(['acquire', current]); }, releaseLock(){ lockLog.push(['release', current]); }})},
  PropertiesService: {getScriptProperties: () => ({getProperty: k => props[k] ?? null, setProperty: (k, v) => { props[k] = v; }})},
  ContentService: {MimeType: {JSON: 'json'}, createTextOutput: s => ({content: s, setMimeType(){ return this; }})},
  Logger: {log: m => console.log('[Logger]', m)},
  console, JSON, Date, Math, Number, String, Set, Object, Array, RegExp,
};
vm.createContext(ctx);
vm.runInContext(code, ctx);

http.createServer((req, res) => {
  const cors = {'Access-Control-Allow-Origin': '*', 'Content-Type': 'application/json'};
  const send = (o) => { res.writeHead(200, cors); res.end(typeof o === 'string' ? o : JSON.stringify(o)); };
  if (req.url.startsWith('/__offline')){ offline = req.url.endsWith('on'); return send({offline}); }
  if (req.url.startsWith('/__delay/')){ delayMs = Number(req.url.split('/').pop()) || 0; return send({delayMs}); }
  if (req.url.startsWith('/__prop?')){ const q = new URL(req.url, 'http://x').searchParams; props[q.get('k')] = q.get('v'); return send({ok: true}); }
  if (req.url.startsWith('/__seed_old_sessions')){   // a sessions tab as created by v6.1 (28 columns, one row)
    const sh = makeSheet('sessions'); sheets.sessions = sh;
    const old = ['sessionId','pid','condAssigned','condFinal','assignedBy','appVersion','lang','consentAt','taskStartAt','taskEndAt','taskEndReason','taskDurationMs','orderCount','lastOrderTotal','overBudget','protectionKept','trialKept','membershipActive','marketingEmail','patternsOn','patternsSeen','phase','withdrawn','completionCode','userAgent','lastSeq','firstSeen','lastUpdate'];
    sh.appendRow(old); sh.appendRow(['00000000-0000-4000-8000-000000000000', 'OLD1', 'control'].concat(Array(25).fill('')));
    return send({ok: true});
  }
  if (req.url.startsWith('/__dump')) return send({sheets: Object.fromEntries(Object.entries(sheets).map(([k, s]) => [k, s.data])), props, formulas, lockLog});
  if (req.url.startsWith('/__purge')){ current = 'purgeWithdrawn'; ctx.purgeWithdrawn(); current = null; return send({ok: true}); }
  if (req.url.startsWith('/__post')){   // direct server-side POST, used to simulate an outdated client
    let body = ''; req.on('data', d => body += d); req.on('end', () => { current = 'doPost'; const out = ctx.doPost({postData: {contents: body}}); current = null; send(out.content); });
    return;
  }
  if (offline){ req.destroy(); return; }
  if (req.method === 'GET'){ current = 'doGet'; const o = ctx.doGet({}).content; current = null; return send(o); }
  if (req.method === 'POST'){
    let body = ''; req.on('data', d => body += d); req.on('end', () => setTimeout(() => {
      current = 'doPost'; const out = ctx.doPost({postData: {contents: body}}); current = null; send(out.content);
    }, delayMs));
    return;
  }
  res.writeHead(405, cors); res.end('{}');
}).listen(PORT, () => console.log('mock apps script on', PORT));
