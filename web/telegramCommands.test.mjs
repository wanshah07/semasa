import assert from 'node:assert/strict';
import { test } from 'node:test';

const api = await import('../supabase/functions/semasa-telegram/commands.js').catch(e => {
  if (e.code === 'ERR_MODULE_NOT_FOUND') return {};
  throw e;
});
const update = (text, extra = {}) => ({ message: { text, from: { id: 42 }, chat: { id: 42, type: 'private' }, ...extra } });
const gate = { kind: 'private', owner: true };
const options = { chatId: 42, now: new Date('2026-11-08T16:30:00Z'), site: 'https://socialmedia.kkmhalalconsultant.com/', username: 'Wan' };

test('menu and help render existing worker callback namespaces without approvals', () => {
  assert.equal(typeof api.commandReply, 'function', 'reply renderer is not implemented');
  const menu = api.commandReply('menu', {}, options);
  assert.equal(menu.method, 'sendMessage');
  assert.equal(menu.chat_id, 42);
  assert.match(menu.text, /Hai Wan/);
  const buttons = menu.reply_markup.inline_keyboard.flat();
  assert.deepEqual(buttons.filter(b => b.callback_data).map(b => b.callback_data), ['menu:draf','menu:jadual','menu:idea','menu:poster','menu:karusel','menu:motion','menu:laporan','menu:robot','menu:kesihatan','menu:ralat','menu:status','menu:bil','menu:memori','menu:ingat']);
  assert.equal(buttons.at(-1).url, options.site);
  const help = api.commandReply('help', {}, options);
  for (const command of ['draf','jadual','status','bil','kesihatan','robot','poster','motion','ingat','menu']) assert.ok(help.text.includes('/' + command));
  assert.equal(api.commandReply('draf', {}, options), null);
  assert.equal(api.commandReply('robot', {}, options), null);
  assert.equal(api.commandReply('menu', {}, { ...options, chatId: null }), null);
  assert.ok(!menu.parse_mode);
  assert.ok(!help.text.includes('—'));
});

test('schedule uses MYT today through day seven inclusive, sorts and caps hook text', () => {
  const p = (date, slot, status, hook, stream = 'regulab') => ({ date, slot, status, hook, stream });
  const posts = [p('2026-11-16','10:00','scheduled','LAST'), p('2026-11-09','12:00','approved','A'.repeat(90)), p('2026-11-08','10:00','draft','PAST'), p('2026-11-17','10:00','draft','FUTURE'), p('2026-11-10','09:00','error','FAILED'), p('2026-11-09','09:00','posted','FIRST','linkedin')];
  const reply = api.commandReply('jadual', { posts }, options);
  assert.ok(reply, 'schedule renderer is not implemented');
  assert.match(reply.text, /2026-11-09/);
  assert.match(reply.text, /2026-11-16/);
  assert.match(reply.text, /📤 09:00 LinkedIn · FIRST/);
  assert.match(reply.text, /✅ 12:00 ws.regulab/);
  assert.ok(reply.text.indexOf('FIRST') < reply.text.indexOf('AAAA'));
  assert.ok(reply.text.includes('A'.repeat(60)));
  assert.ok(!reply.text.includes('A'.repeat(61)));
  for (const absent of ['PAST','FUTURE','FAILED','—']) assert.ok(!reply.text.includes(absent));
  assert.match(api.commandReply('jadual', { posts: [] }, options).text, /Tiada post/);
  assert.equal(api.commandReply('jadual', {}, options), null);
  assert.equal(api.commandReply('jadual', { posts: [{ status: 'draft', date: 'bad' }] }, options), null);
  const many = Array.from({ length: 200 }, (_, i) => p('2026-11-09','09:00','draft', `${i} ${'📝'.repeat(80)}`));
  const text = api.commandReply('jadual', { posts: many }, options).text;
  assert.ok(text.length <= 4000);
  assert.match(text, /Dipendekkan/);
  assert.ok(!/[\uD800-\uDBFF]$/.test(text));
});

test('status counts publisher errors, writing and recent failures without echoing error objects', () => {
  const data = { posts: [{status:'draft',errors:{scan:'SECRET',at:'SECRET'}},{status:'approved',errors:{buffer:{message:'SECRET'}}},{status:'scheduled',errors:{}}], ideas: [{status:'new'},{status:'working'},{status:'error',updated_at:'2026-11-01T16:30:00Z'},{status:'error',updated_at:'2026-10-31T16:30:00Z'}], health: { problems: [{area:'system',what:'SECRET'}] } };
  const reply = api.commandReply('status', data, options);
  assert.ok(reply, 'status renderer is not implemented');
  for (const line of ['09/11 00:30 MYT','Draf menunggu: 1','Diluluskan: 1','Dijadualkan: 1','Idea sedang ditulis: 2','Idea gagal (7 hari): 1','Post dengan ralat penerbit: 1','Masalah watchdog terbuka: 1']) assert.ok(reply.text.includes(line), line);
  assert.ok(!reply.text.includes('SECRET'));
  assert.equal(api.commandReply('status', { ...data, ideas: null }, options), null);
  assert.equal(api.commandReply('status', { ...data, health: null }, options), null);
  assert.equal(api.commandReply('status', data, {...options, now: new Date('bad')}), null);
});

test('health shows at most twelve problems and redacts credentials from diagnostic text', () => {
  const problems = [{area:'api',what:'Gagal Bearer private-token-123 sk-secretkey1234567890',todo:'Semak https://host.test/path?api_key=hidden-query dan token=hidden-value'}, ...Array.from({length:12}, (_,i) => ({area:'system',what:`Masalah ${i}`}))];
  const reply = api.commandReply('kesihatan', {health:{problems}}, options);
  assert.ok(reply, 'health renderer is not implemented');
  assert.match(reply.text, /Perlu perhatian/);
  assert.match(reply.text, /Semak/);
  for (const secret of ['private-token-123','sk-secretkey1234567890','hidden-query','hidden-value','Masalah 11']) assert.ok(!reply.text.includes(secret), secret);
  assert.equal(api.commandReply('kesihatan', {}, options), null);
  assert.match(api.commandReply('kesihatan', {health:{problems:[]}}, options).text, /Semua berjalan baik/);
  assert.equal(api.commandReply('kesihatan', {health:{problems:[null]}}, options), null);
  const menu = api.commandReply('menu', {}, {...options,username:'Wan — token=hidden-value'});
  assert.ok(!menu.text.includes('hidden-value'));
  assert.ok(!menu.text.includes('—'));
});

test('billing sorts open documents and totals invoices per currency across the full result', () => {
  const invoice = (number, total, currency = 'MYR', due_date = null) => ({kind:'invoice',number,total,currency,due_date,status:'sent',client:{name:'Pelanggan'}});
  const billingDocs = [invoice('INV-2',1000.5,'MYR','2026-12-01'), {...invoice('QT-1',2000,'MYR','2026-11-09'),kind:'quotation'}, invoice('USD-1','12.3','USD','2026-11-10'), invoice('PAID',999,'MYR','2026-11-01')];
  billingDocs.at(-1).status = 'paid';
  const reply = api.commandReply('bil', {billingDocs}, options);
  assert.ok(reply, 'billing renderer is not implemented');
  assert.ok(reply.text.indexOf('QT-1') < reply.text.indexOf('INV-2'));
  assert.match(reply.text, /MYR 1,000\.50/);
  assert.match(reply.text, /USD 12\.30/);
  assert.ok(!reply.text.includes('PAID'));
  assert.match(reply.text, /Jumlah invois belum dibayar: MYR 1,000\.50, USD 12\.30/);
  const many = Array.from({length:16},(_,i)=>invoice(`INV-${i}`,100));
  const long = api.commandReply('bil', {billingDocs:many}, options).text;
  assert.match(long, /MYR 1,600\.00/);
  assert.match(long, /15 daripada 16/);
  assert.ok(!long.includes('INV-15'));
  assert.equal(api.commandReply('bil', {}, options), null);
  assert.equal(api.commandReply('bil', {billingDocs:[invoice('BAD','oops')]}, options), null);
  assert.match(api.commandReply('bil', {billingDocs:[]}, options).text, /Tiada invois/);
});

const link = { telegram_user_id: 42, user_id: 'owner-user', username: 'Wan' };
function mockDb(fixtures = {}) {
  const calls = [];
  return { calls, from(table) {
    const call = { table, filters: [] }; calls.push(call);
    const query = {
      select(columns) { call.columns = columns; return query; },
      eq(...args) { call.filters.push(['eq', ...args]); return query; },
      in(...args) { call.filters.push(['in', ...args]); return query; },
      gte(...args) { call.filters.push(['gte', ...args]); return query; },
      lte(...args) { call.filters.push(['lte', ...args]); return query; },
      limit(n) { call.limit = n; return query; },
      maybeSingle() { call.single = true; return query; },
      then(resolve, reject) {
        const key = call.filters.find(f => f[0] === 'eq' && f[1] === 'key')?.[2];
        const fixture = fixtures[key || table];
        if (fixture instanceof Error) return Promise.reject(fixture).then(resolve, reject);
        return Promise.resolve(fixture ?? {data:null,error:null}).then(resolve, reject);
      },
    };
    return query;
  } };
}

test('orchestrator rechecks identity and pending state before serving a menu without writes', async () => {
  assert.equal(typeof api.fastCommand, 'function', 'DB command orchestrator is not implemented');
  const db = mockDb({telegram_chat:{data:{value:{}},error:null}});
  assert.equal(await api.fastCommand(db, update('/menu'), null, options), null);
  assert.equal(await api.fastCommand(db, update('/menu'), {...link,telegram_user_id:99}, options), null);
  assert.equal(await api.fastCommand(db, update('/menu'), {...link,user_id:null}, options), null);
  assert.equal(await api.fastCommand(db, update('/menu'), link, {...options,busy:true}), null);
  assert.equal(await api.fastCommand(db, {callback_query:{data:'menu:jadual',from:{id:42}}}, link, options), null);
  assert.equal(db.calls.length, 0);
  const reply = await api.fastCommand(db, update('/menu'), link, options);
  assert.match(reply.text, /Hai Wan/);
  assert.deepEqual(db.calls.map(c=>c.table), ['semasa_settings']);
  for (const state of [{pending:'poster'},{await_note:true}]) {
    const pending = mockDb({telegram_chat:{data:{value:state},error:null}});
    assert.equal(await api.fastCommand(pending, update('/status'), link, options), null);
    assert.equal(pending.calls.length, 1);
  }
  for (const fixture of [{data:null,error:null},{data:{value:{}},error:{message:'SECRET'}},new Error('SECRET')]) {
    assert.equal(await api.fastCommand(mockDb({telegram_chat:fixture}), update('/menu'), link, options), null);
  }
});

test('schedule orchestrator reads only the bounded MYT date range and falls back on errors or capped data', async () => {
  const posts = [{date:'2026-11-09',slot:'10:00',stream:'regulab',status:'draft',hook:'Topik'}];
  const db = mockDb({semasa_posts:{data:posts,error:null}});
  const reply = await api.fastCommand(db, update('/jadual'), link, {...options,state:{}});
  assert.ok(reply, 'schedule DB read is not implemented');
  assert.match(reply.text, /Topik/);
  assert.deepEqual(db.calls[0].filters, [['in','status',['draft','approved','scheduled','posted']],['gte','date','2026-11-09'],['lte','date','2026-11-16']]);
  assert.equal(db.calls[0].table, 'semasa_posts');
  assert.ok(!db.calls[0].columns.includes('*'));
  for (const fixture of [{data:null,error:null},{data:posts,error:{message:'SECRET'}},new Error('SECRET'),{data:Array.from({length:1000},()=>posts[0]),error:null}]) {
    assert.equal(await api.fastCommand(mockDb({semasa_posts:fixture}), update('/jadual'), link, {...options,state:{}}), null);
  }
  assert.match((await api.fastCommand(mockDb({semasa_posts:{data:[],error:null}}), update('/jadual'), link, {...options,state:{}})).text, /Tiada post/);
});

test('status DB path needs complete posts, ideas and watchdog state; any failed read falls back', async () => {
  const fixtures = {semasa_posts:{data:[{status:'draft'}],error:null},semasa_ideas:{data:[{status:'working'}],error:null},health_state:{data:{value:{problems:[]}},error:null}};
  const db = mockDb(fixtures);
  const reply = await api.fastCommand(db, update('/status'), link, {...options,state:{}});
  assert.ok(reply, 'status DB reads are not implemented');
  assert.match(reply.text, /Draf menunggu: 1/);
  assert.match(reply.text, /Idea sedang ditulis: 1/);
  assert.deepEqual(db.calls.map(c=>c.table).sort(), ['semasa_ideas','semasa_posts','semasa_settings']);
  for (const key of Object.keys(fixtures)) for (const fixture of [{data:null,error:null},{...fixtures[key],error:{message:'token=secret'}},new Error('secret')]) {
    assert.equal(await api.fastCommand(mockDb({...fixtures,[key]:fixture}),update('/status'),link,{...options,state:{}}),null, key);
  }
  assert.equal(await api.fastCommand(mockDb({...fixtures,semasa_posts:{data:[],error:null,count:10}}),update('/status'),link,{...options,state:{}}),null);
});

test('health and billing DB paths are read-only and return null on missing, rejected or failed reads', async () => {
  for (const [command,table,fixture,expected] of [
    ['kesihatan','health_state',{data:{value:{problems:[]}},error:null},/Semua berjalan baik/],
    ['bil','semasa_billing_docs',{data:[{kind:'invoice',number:'INV-1',status:'issued',total:20}],error:null},/MYR 20\.00/],
  ]) {
    const db = mockDb({[table]:fixture});
    const reply = await api.fastCommand(db, update('/'+command), link, {...options,state:{}});
    assert.ok(reply, command + ' DB read is not implemented');
    assert.match(reply.text, expected);
    assert.equal(db.calls.length, 1);
    assert.ok(!db.calls[0].columns.includes('*'));
    if (command === 'bil') assert.deepEqual(db.calls[0].filters, [['in','status',['issued','sent','viewed']]]);
    for (const failed of [{data:null,error:null},{...fixture,error:{message:'secret'}},new Error('secret')]) {
      assert.equal(await api.fastCommand(mockDb({[table]:failed}),update('/'+command),link,{...options,state:{}}),null);
    }
  }
});

test('malformed commands and corrupt records fail closed, including prototype property names', () => {
  for (const text of ['/constructor','/toString','/__proto__']) assert.equal(api.fastCommandOf(update(text),gate),null);
  for (const site of ['javascript:alert(1)','https://user:secret@site.test/','https://site.test/?token=secret','not-a-url']) assert.equal(api.commandReply('menu',{}, {...options,site}),null);
  assert.equal(api.commandReply('status',{posts:[{}],ideas:[],health:{problems:[]}},options),null);
  assert.equal(api.commandReply('status',{posts:[],ideas:[{status:'error',updated_at:'invalid'}],health:{problems:[]}},options),null);
  assert.equal(api.commandReply('jadual',{posts:[{status:'draft',date:'2026-99-99'}]},options),null);
  const text = api.commandReply('kesihatan',{health:{problems:[{area:'api',what:'JSON {"api_key": "json-secret", "password": "private-pass"}'}]}},options).text;
  assert.ok(!text.includes('json-secret'));
  assert.ok(!text.includes('private-pass'));
});

test('only exact read commands from an idle linked private sender are eligible', () => {
  assert.equal(typeof api.fastCommandOf, 'function', 'command classifier is not implemented');
  for (const [text, command] of [['/menu','menu'],['/start','menu'],['/help','help'],['/bantuan','help'],['/STATUS@SocialMediaWan_bot','status'],[' /jadual ','jadual'],['/bil','bil'],['/kesihatan','kesihatan']]) {
    assert.equal(api.fastCommandOf(update(text), gate), command);
    assert.equal(api.fastCommandOf(update(text), { ...gate, owner: false }), null);
    assert.equal(api.fastCommandOf(update(text), { ...gate, busy: true }), null);
    assert.equal(api.fastCommandOf(update(text, { chat: { id: -1, type: 'group' } }), gate), null);
  }
  for (const text of ['/start ABCD1234', '/menu topic', '/draf', '/robot', '/idea x', 'status', '/status\n/ingat x']) assert.equal(api.fastCommandOf(update(text), gate), null);
  assert.equal(api.fastCommandOf({ callback_query: { data: 'menu:status' } }, gate), null);
  assert.equal(api.fastCommandOf(update('/status'), { ...gate, kind: 'callback' }), null);
});
