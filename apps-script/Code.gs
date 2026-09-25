/**
 * Semasa — the Google Sheet made for Semasa. One sheet, two jobs:
 *
 *   FAQ   "Semua FAQ" plus one tab per category, a mirror of the ready entries in semasa_faqs. The worker
 *         (backend/semasa/faq.py) POSTs the WHOLE list whenever it changes and this script REPLACES the tabs.
 *         The database is the source of truth: an edit made IN the sheet is overwritten. Edit FAQs in Semasa.
 *   Log   the "Log" tab, a running copy of semasa_log. Every run (scrape, worker, publisher) POSTs the rows the
 *         sheet has not had yet (backend/semasa/sheet.py) and this script APPENDS them. Each row carries the
 *         log's own id and LAST_LOG_ID remembers the highest one written, so a row sent twice is written once.
 *         The database keeps 90 days; this tab keeps the newest LOG_KEEP rows, so it is the long record.
 *
 * Setup (the same routine as the KKM complaint sheet):
 *   1. Make a Google Sheet named "Semasa". Extensions → Apps Script. Paste this file as Code.gs and
 *      appsscript.json as the manifest (Project Settings → show "appsscript.json" manifest file).
 *   2. Run `setup` once and allow access. The log prints API_TOKEN.
 *   3. Deploy → New deployment → Web app: Execute as "Me", Who has access "Anyone". Copy the /exec URL.
 *      (Changing this file later: Deploy → Manage deployments → edit → Version "New version". Same URL.)
 *   4. GitHub → wanshah07/semasa → Settings → Secrets and variables → Actions → New secret:
 *        SEMASA_SHEET_URL    the /exec URL
 *        SEMASA_SHEET_TOKEN  the API_TOKEN from step 2
 *      (FAQ_SHEET_URL / FAQ_SHEET_TOKEN, the first names of these two, still work.)
 *   "Anyone" is safe because every call must carry the token; a call without it is refused.
 */

var PROPS = PropertiesService.getScriptProperties();
var MAIN_TAB = 'Semua FAQ';
var LOG_TAB = 'Log';
var LOG_KEEP = 50000;                                   // newest rows kept in the Log tab
var LOG_HEADERS = {
  id: 'ID', at_myt: 'Masa (MYT)', level: 'Tahap', area: 'Bahagian', event: 'Peristiwa', title: 'Apa berlaku',
  actor: 'Oleh', ref_table: 'Jadual', ref_id: 'Rujukan', detail: 'Butiran'
};
var HEADERS = {
  id: 'ID', category_bm: 'Kategori', subcategory: 'Subkategori',
  question_bm: 'Soalan (BM)', answer_bm: 'Jawapan (BM)', question_en: 'Question (EN)', answer_en: 'Answer (EN)',
  tags: 'Tag', needs_check: 'Perlu semakan', check_note: 'Nota semakan', instrument: 'Instrumen / sumber rasmi',
  answer_source: 'Jawapan oleh', source_kind: 'Masuk melalui', source_name: 'Sumber asal', source_url: 'Pautan sumber',
  created_at: 'Dicipta', updated_at: 'Dikemas kini'
};

function setup() {
  if (!PROPS.getProperty('API_TOKEN')) PROPS.setProperty('API_TOKEN', randomToken_(40));
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  if (!ss.getSheetByName(MAIN_TAB)) ss.insertSheet(MAIN_TAB, 0);
  Logger.log('Setup complete.\nAPI_TOKEN=%s', PROPS.getProperty('API_TOKEN'));
  return { ok: true, apiToken: PROPS.getProperty('API_TOKEN') };
}

function doPost(e) {
  var body;
  try {
    body = JSON.parse((e && e.postData && e.postData.contents) || '{}');
  } catch (err) {
    return json_({ ok: false, error: 'Invalid JSON body' });
  }
  if (body.action === 'ping') return json_({ ok: true, time: new Date().toISOString() });
  if (!checkToken_(body.token)) return json_({ ok: false, error: 'Unauthorised' });
  try {
    if (body.action === 'replace') return json_(replaceAll_(body.fields || Object.keys(HEADERS), body.rows || []));
    if (body.action === 'append_log') return json_(appendLog_(body.fields || Object.keys(LOG_HEADERS), body.rows || []));
    return json_({ ok: false, error: 'Unknown action ' + body.action });
  } catch (err) {
    return json_({ ok: false, error: String(err && err.message || err) });
  }
}

function doGet() {
  return json_({ ok: true, service: 'Semasa sheet', rows: rowCount_(), lastLogId: Number(PROPS.getProperty('LAST_LOG_ID') || 0) });
}

function replaceAll_(fields, rows) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var head = fields.map(function (f) { return HEADERS[f] || f; });
    writeTab_(ss, MAIN_TAB, head, rows.map(function (r) { return fields.map(function (f) { return cell_(r[f]); }); }), 0);

    // one tab per category, in the order the rows arrive (the worker sorts them by the category list)
    var byCat = {}, order = [];
    rows.forEach(function (r) {
      var k = String(r.category_bm || 'Lain-lain');
      if (!byCat[k]) { byCat[k] = []; order.push(k); }
      byCat[k].push(fields.map(function (f) { return cell_(r[f]); }));
    });
    var managed = JSON.parse(PROPS.getProperty('CATEGORY_TABS') || '[]');
    order.forEach(function (k, i) { writeTab_(ss, tabName_(k), head, byCat[k], i + 1); });
    var now = order.map(tabName_);
    managed.forEach(function (name) {                     // a category with no entries left loses its tab
      if (now.indexOf(name) < 0 && name !== MAIN_TAB) {
        var sh = ss.getSheetByName(name);
        if (sh) ss.deleteSheet(sh);
      }
    });
    PROPS.setProperty('CATEGORY_TABS', JSON.stringify(now));
    PROPS.setProperty('LAST_SYNC', new Date().toISOString());
    return { ok: true, rows: rows.length, tabs: now.length + 1 };
  } finally {
    lock.releaseLock();
  }
}

function appendLog_(fields, rows) {
  var lock = LockService.getScriptLock();
  lock.waitLock(30000);
  try {
    var ss = SpreadsheetApp.getActiveSpreadsheet();
    var head = fields.map(function (f) { return LOG_HEADERS[f] || f; });
    var sh = ss.getSheetByName(LOG_TAB);
    if (!sh) {
      sh = ss.insertSheet(LOG_TAB, ss.getSheets().length);
      sh.getRange(1, 1, 1, head.length).setValues([head]).setFontWeight('bold').setBackground('#f4eee4');
      sh.setFrozenRows(1);
      var widths = { 'Masa (MYT)': 150, 'Apa berlaku': 460, 'Butiran': 320, 'Peristiwa': 170 };
      head.forEach(function (h, i) { sh.setColumnWidth(i + 1, widths[h] || 100); });
    }
    var last = Number(PROPS.getProperty('LAST_LOG_ID') || 0);
    var fresh = rows.filter(function (r) { return Number(r.id) > last; })
                    .sort(function (a, b) { return Number(a.id) - Number(b.id); });
    if (!fresh.length) return { ok: true, appended: 0, lastLogId: last };
    var values = fresh.map(function (r) { return fields.map(function (f) { return cell_(r[f]); }); });
    var start = sh.getLastRow() + 1;
    ensureRows_(sh, start + values.length - 1);
    sh.getRange(start, 1, values.length, head.length).setValues(values).setVerticalAlignment('top');
    var colours = { error: '#fde8e8', warn: '#fff4dc' };
    fresh.forEach(function (r, i) {                       // errors and warnings stand out when scrolling
      if (colours[r.level]) sh.getRange(start + i, 1, 1, head.length).setBackground(colours[r.level]);
    });
    var extra = sh.getLastRow() - 1 - LOG_KEEP;
    if (extra > 0) sh.deleteRows(2, extra);
    last = Number(fresh[fresh.length - 1].id);
    PROPS.setProperty('LAST_LOG_ID', String(last));
    return { ok: true, appended: fresh.length, lastLogId: last };
  } finally {
    lock.releaseLock();
  }
}

function writeTab_(ss, name, head, values, index) {
  var sh = ss.getSheetByName(name) || ss.insertSheet(name, Math.min(index, ss.getSheets().length));
  sh.clear();
  if (sh.getFilter()) sh.getFilter().remove();
  sh.getRange(1, 1, 1, head.length).setValues([head]).setFontWeight('bold').setBackground('#f4eee4');
  ensureRows_(sh, values.length + 1);
  if (values.length) sh.getRange(2, 1, values.length, head.length).setValues(values).setWrap(true).setVerticalAlignment('top');
  sh.setFrozenRows(1);
  sh.getRange(1, 1, Math.max(values.length + 1, 2), head.length).createFilter();
  var widths = { 'Soalan (BM)': 320, 'Jawapan (BM)': 420, 'Question (EN)': 320, 'Answer (EN)': 420, 'Nota semakan': 240 };
  head.forEach(function (h, i) { sh.setColumnWidth(i + 1, widths[h] || 140); });
  return sh;
}

// A new tab has 1000 rows, and a range past the last row is refused: grow the tab first.
function ensureRows_(sh, lastRow) {
  var have = sh.getMaxRows();
  if (lastRow > have) sh.insertRowsAfter(have, lastRow - have);
}

function tabName_(label) {
  var name = String(label).replace(/[\[\]\*\?\/\\:]/g, ' ').slice(0, 90) || 'Lain-lain';
  return (name === LOG_TAB || name === MAIN_TAB) ? name + ' (FAQ)' : name;   // a category never takes the Log tab
}

function cell_(v) {
  if (v === null || v === undefined) return '';
  var s = String(v);
  return /^[=+\-@]/.test(s) ? "'" + s : s;              // never let a pasted answer run as a formula
}

function rowCount_() {
  var sh = SpreadsheetApp.getActiveSpreadsheet().getSheetByName(MAIN_TAB);
  return sh ? Math.max(0, sh.getLastRow() - 1) : 0;
}

function checkToken_(t) {
  var want = PROPS.getProperty('API_TOKEN');
  return Boolean(want) && t === want;
}

function randomToken_(n) {
  var chars = 'ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789', out = '';
  for (var i = 0; i < n; i++) out += chars.charAt(Math.floor(Math.random() * chars.length));
  return out;
}

function json_(o) {
  return ContentService.createTextOutput(JSON.stringify(o)).setMimeType(ContentService.MimeType.JSON);
}
