const DEFAULT_SITE = 'https://socialmedia.kkmhalalconsultant.com';
const MENU = [
  [['📝 Draf untuk lulus', 'draf'], ['🗓 Jadual 7 hari', 'jadual'], ['💡 Idea baharu', 'idea']],
  [['🎨 Poster', 'poster'], ['🖼 Karusel', 'karusel'], ['🎬 Motion', 'motion'], ['📄 Laporan', 'laporan']],
  [['🤖 Robot AI', 'robot'], ['🩺 Kesihatan', 'kesihatan'], ['❗ Ralat', 'ralat'], ['📊 Status', 'status']],
  [['💰 Bil', 'bil'], ['🧠 Memori', 'memori'], ['✍️ Ingat sesuatu', 'ingat']],
];
const HELP = 'Semasa di Telegram 🤖\n\n' + [
  '/draf · Draf untuk lulus', '/jadual · Jadual 7 hari', '/status · Ringkasan Semasa', '/ralat · Ralat dan cuba lagi',
  '/kesihatan · Masalah watchdog', '/bil · Invois dan sebut harga terbuka', '/idea · Idea daripada topik atau link',
  '/robot · Pilih robot AI', '/poster · Cipta poster', '/karusel · Cipta karusel', '/motion · Cipta Motion',
  '/video · Cipta video', '/laporan · Cipta laporan', '/ingat · Simpan nota', '/memori · Senarai nota',
  '/menu · Menu butang', '/help · Senarai arahan',
].join('\n') + '\n\nHantar link terus untuk jadikan idea. Tanya apa-apa tentang Semasa dalam BM atau English.';

const DAY = 86_400_000;
const mytDate = now => new Date(now.getTime() + 8 * 3_600_000).toISOString().slice(0, 10);
function redact(value) {
  return String(value ?? '').replace(/—/g, '·')
    .replace(/https?:\/\/[^\s<>]+/gi, '[pautan]')
    .replace(/\b(?:Bearer|Basic)\s+[A-Za-z0-9._~+\/-]+=*/gi, '[dirahsiakan]')
    .replace(/\b(?:api[_-]?key|access[_-]?token|refresh[_-]?token|token|secret|password|authorization)["']?\s*[=:]\s*["']?[^\s,"';}]+/gi, '[dirahsiakan]')
    .replace(/\b(?:sk-[A-Za-z0-9_-]{8,}|AIza[A-Za-z0-9_-]{15,}|gh[pousr]_[A-Za-z0-9_]+|github_pat_[A-Za-z0-9_]+|eyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+|\d{6,12}:[A-Za-z0-9_-]{20,})\b/g, '[dirahsiakan]');
}
const clip = (value, max) => Array.from(redact(value)).slice(0, max).join('');
function fit(text) {
  if (text.length <= 4000) return text;
  const suffix = '\n\nDipendekkan. Buka Semasa untuk senarai penuh.';
  let head = text.slice(0, 4000 - suffix.length);
  if (/[\uD800-\uDBFF]$/.test(head)) head = head.slice(0, -1);
  return head + suffix;
}
function schedule(data, now) {
  if (!Array.isArray(data?.posts) || !Number.isFinite(now?.getTime())) return null;
  const today = mytDate(now), end = mytDate(new Date(now.getTime() + 7 * DAY));
  if (data.posts.some(p => !p || !/^\d{4}-\d{2}-\d{2}$/.test(p.date || '') || !Number.isFinite(Date.parse(p.date)) || new Date(p.date).toISOString().slice(0, 10) !== p.date)) return null;
  const icons = { draft: '📝', approved: '✅', scheduled: '🕒', posted: '📤' };
  const rows = data.posts.filter(p => Object.hasOwn(icons, p.status) && p.date >= today && p.date <= end)
    .sort((a, b) => [a.date, a.slot || '', a.stream || ''].join('|').localeCompare([b.date, b.slot || '', b.stream || ''].join('|')));
  if (!rows.length) return 'Tiada post dalam 7 hari akan datang.';
  const lines = ['Jadual 7 hari (📝 draf · ✅ lulus · 🕒 dijadual · 📤 dihantar)'];
  let day;
  for (const p of rows) {
    if (p.date !== day) { day = p.date; lines.push(`\n${day}`); }
    const hook = clip(String(p.hook || p.domain || p.angle || '').trim(), 60);
    const stream = { regulab: 'ws.regulab', linkedin: 'LinkedIn' }[p.stream] || clip(p.stream, 40);
    lines.push(`${icons[p.status]} ${clip(p.slot || '--:--', 8)} ${stream}` + (hook ? ` · ${hook}` : ''));
  }
  return lines.join('\n');
}

function status(data, now) {
  if (!Array.isArray(data?.posts) || !Array.isArray(data?.ideas) || !Array.isArray(data?.health?.problems) || !Number.isFinite(now?.getTime())) return null;
  if (data.posts.some(p => !['draft', 'approved', 'scheduled'].includes(p?.status)) || data.ideas.some(i => !['new', 'working', 'error'].includes(i?.status) || (i.status === 'error' && !Number.isFinite(Date.parse(i.updated_at))))) return null;
  const count = s => data.posts.filter(p => p?.status === s).length;
  const errs = data.posts.filter(p => p?.errors && Object.keys(p.errors).some(k => !['scan', 'at'].includes(k))).length;
  const writing = data.ideas.filter(i => ['new', 'working'].includes(i?.status)).length;
  const since = now.getTime() - 7 * DAY;
  const failed = data.ideas.filter(i => i?.status === 'error' && Date.parse(i.updated_at) >= since).length;
  const stamp = new Date(now.getTime() + 8 * 3_600_000).toISOString();
  return `Semasa sekarang (${stamp.slice(8, 10)}/${stamp.slice(5, 7)} ${stamp.slice(11, 16)} MYT)\n` +
    `📝 Draf menunggu: ${count('draft')}\n✅ Diluluskan: ${count('approved')}\n🕒 Dijadualkan: ${count('scheduled')}\n` +
    `✍️ Idea sedang ditulis: ${writing}\n❗ Idea gagal (7 hari): ${failed}\n📮 Post dengan ralat penerbit: ${errs}\n` +
    `🩺 Masalah watchdog terbuka: ${data.health.problems.length}\n\n/draf untuk lulus · /ralat untuk ralat · /kesihatan untuk masalah`;
}

function health(data) {
  const problems = data?.health?.problems;
  if (!Array.isArray(problems) || problems.some(p => !p || typeof p !== 'object' || typeof p.what !== 'string' || typeof p.area !== 'string')) return null;
  if (!problems.length) return '🩺 Semua berjalan baik.';
  return '🩺 Perlu perhatian:\n' + problems.slice(0, 12).map(p => `• ${clip(p.area, 80)}: ${clip(p.what, 300)}` + (p.todo ? `\n  → ${clip(p.todo, 200)}` : '')).join('\n');
}

const OPEN = ['issued', 'sent', 'viewed'];
function billing(data) {
  if (!Array.isArray(data?.billingDocs) || data.billingDocs.some(d => !d || !Number.isFinite(Number(d.total ?? 0)))) return null;
  const rows = data.billingDocs.filter(d => OPEN.includes(d.status)).sort((a, b) => String(a.due_date || '9999').localeCompare(String(b.due_date || '9999')));
  if (!rows.length) return '💰 Tiada invois atau sebut harga terbuka.';
  const money = n => Number(n).toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const totals = new Map();
  // Count all open invoices, even when only the first fifteen documents fit in the list.
  for (const d of rows) if (d.kind === 'invoice') {
    const cur = d.currency || 'MYR';
    totals.set(cur, (totals.get(cur) || 0) + Number(d.total || 0));
  }
  const lines = ['💰 Terbuka (belum dibayar / belum diterima):'];
  for (const d of rows.slice(0, 15)) lines.push(`• ${clip(d.number, 60)} · ${clip(d.client?.name, 40)} · ${clip(d.currency || 'MYR', 8)} ${money(d.total || 0)} · tarikh akhir ${clip(d.due_date || '-', 10)}`);
  if (rows.length > 15) lines.push(`\nDipaparkan 15 daripada ${rows.length} dokumen.`);
  if (totals.size) lines.push('\nJumlah invois belum dibayar: ' + [...totals].sort(([a], [b]) => a.localeCompare(b)).map(([c, v]) => `${clip(c, 8)} ${money(v)}`).join(', '));
  return lines.join('\n');
}

export function commandReply(command, data, { chatId, now = new Date(), site = DEFAULT_SITE, username = 'Wan' } = {}) {
  if (chatId == null) return null;
  let text, keyboard;
  if (command === 'menu') {
    try {
      const url = new URL(site);
      if (url.protocol !== 'https:' || url.username || url.password || url.search || url.hash) return null;
    } catch { return null; }
    text = `Hai ${username || 'Wan'} 👋 Semasa di sini.\n\nPilih di bawah, atau terus taip soalan. Saya ingat nota anda dan belajar daripada 👍/👎 di bawah setiap jawapan.\n\n/menu bila-bila masa untuk menu ini.`;
    keyboard = MENU.flatMap(group => {
      const rows = [];
      for (let i = 0; i < group.length; i += 2) rows.push(group.slice(i, i + 2).map(([label, action]) => ({ text: label, callback_data: `menu:${action}` })));
      return rows;
    });
    keyboard.push([{ text: '🔗 Buka Semasa', url: site.replace(/\/+$/, '') + '/' }]);
  } else if (command === 'help') text = HELP;
  else if (command === 'jadual') text = schedule(data, now);
  else if (command === 'status') text = status(data, now);
  else if (command === 'kesihatan') text = health(data);
  else if (command === 'bil') text = billing(data);
  else return null;
  if (text == null) return null;
  return { method: 'sendMessage', chat_id: chatId, text: fit(redact(text)), ...(keyboard ? { reply_markup: { inline_keyboard: keyboard } } : {}) };
}

const object = value => value !== null && typeof value === 'object' && !Array.isArray(value);
async function setting(db, key) {
  const result = await db.from('semasa_settings').select('value').eq('key', key).maybeSingle();
  if (result?.error || !object(result?.data?.value)) throw new Error('Setting not readable');
  return result.data.value;
}

async function rows(query) {
  const result = await query.limit(1000);
  // A capped PostgREST result must not become a partial count or financial total.
  if (result?.error || !Array.isArray(result?.data) || result.data.length >= 1000 || (result.count != null && result.count !== result.data.length)) throw new Error('Rows not complete');
  return result.data;
}

// The caller checks recent unfinished inbox rows and passes busy; unreadable means busy.
// An optional state is a fresh telegram_chat value already read by the caller, not an empty substitute after a read error.
export async function fastCommand(db, update, link, { now = new Date(), site = DEFAULT_SITE, busy = false, state } = {}) {
  const from = update?.message?.from?.id;
  const owner = !!link?.user_id && /^\d+$/.test(String(from)) && String(from) === String(link?.telegram_user_id);
  const command = fastCommandOf(update, { kind: update?.message?.chat?.type, owner, busy });
  if (!command) return null;
  try {
    const chatState = state === undefined ? await setting(db, 'telegram_chat') : state;
    if (!object(chatState) || chatState.pending || chatState.await_note) return null;
    const data = {};
    if (command === 'jadual') data.posts = await rows(db.from('semasa_posts').select('date,slot,stream,status,hook,domain,angle', { count: 'exact' })
      .in('status', ['draft', 'approved', 'scheduled', 'posted']).gte('date', mytDate(now)).lte('date', mytDate(new Date(now.getTime() + 7 * DAY))));
    if (command === 'status') [data.posts, data.ideas, data.health] = await Promise.all([
      rows(db.from('semasa_posts').select('status,date,errors', { count: 'exact' }).in('status', ['draft', 'approved', 'scheduled'])),
      rows(db.from('semasa_ideas').select('status,updated_at', { count: 'exact' }).in('status', ['new', 'working', 'error'])),
      setting(db, 'health_state'),
    ]);
    if (command === 'kesihatan') data.health = await setting(db, 'health_state');
    if (command === 'bil') data.billingDocs = await rows(db.from('semasa_billing_docs').select('kind,number,status,total,currency,due_date,client', { count: 'exact' }).in('status', OPEN));
    return commandReply(command, data, { chatId: update.message.chat.id, now, site, username: link.username });
  } catch {
    return null;
  }
}

const COMMANDS = { menu: 'menu', start: 'menu', help: 'help', bantuan: 'help', status: 'status', jadual: 'jadual', bil: 'bil', kesihatan: 'kesihatan' };

export function fastCommandOf(update, { kind, owner, busy = false } = {}) {
  if (kind !== 'private' || !owner || busy || update?.callback_query || update?.message?.chat?.type !== 'private') return null;
  const match = typeof update.message.text === 'string' && update.message.text.trim().match(/^\/([a-z]+)(?:@[a-z0-9_]+)?$/i);
  const name = match ? match[1].toLowerCase() : '';
  return Object.hasOwn(COMMANDS, name) ? COMMANDS[name] : null;
}
