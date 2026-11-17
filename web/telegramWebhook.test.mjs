// Exercise the actual webhook entrypoint with only the database/network boundary replaced.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
const entry = new URL('../supabase/functions/semasa-telegram/index.ts', import.meta.url);
let handler;
let writes=[];
let pending=null;
let busy=false;
let duplicate=false;
const link={telegram_user_id:111,user_id:'user-1',username:'Wan'};
const db={from(table){
  const q={ table, key:null, op:'select', row:null,
    select(){return this;}, eq(k,v){if(k==='key')this.key=v;return this;},
    in(){return this;},gte(){return this;},order(){return this;},limit(){return this;},
    upsert(row){this.op='upsert';this.row=row;writes.push(row);return this;},
    maybeSingle(){return Promise.resolve(this.result(true));},
    result(single=false){
      if(this.op==='upsert')return {data:single?(duplicate?null:{id:77}):[],error:null};
      if(table==='semasa_telegram_link')return {data:link,error:null};
      if(table==='semasa_settings')return {data:{value:this.key==='telegram_chat'?{pending}:{}},error:null};
      if(table==='semasa_telegram_inbox')return {data:busy?[{id:1}]:[],error:null};
      return {data:[],error:null};
    },
    then(resolve,reject){return Promise.resolve(this.result()).then(resolve,reject);},
  };return q;
}};
globalThis.__telegramTestClient=()=>db;
globalThis.Deno={env:{get:(key)=>key==='TELEGRAM_WEBHOOK_SECRET'?'test-signature':'https://project.supabase.co'},serve:fn=>{handler=fn;}};
let source=ts.transpileModule(readFileSync(entry,'utf8'),{compilerOptions:{module:ts.ModuleKind.ESNext,target:ts.ScriptTarget.ES2022}}).outputText;
source=source.replace(/import \{ createClient \} from "npm:@supabase\/supabase-js@2";/,'const createClient=globalThis.__telegramTestClient;');
source=source.replace(/from "(\.[^"]+)"/g,(_all,path)=>`from ${JSON.stringify(new URL(path,entry).href)}`);
await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'));
const update=(text,from=111)=>({update_id:100,message:{message_id:5,from:{id:from},chat:{id:from,type:'private'},text}});
const request=(payload,secret='test-signature',probe=false)=>new Request('https://function.example',{method:'POST',headers:{'Content-Type':'application/json','X-Telegram-Bot-Api-Secret-Token':secret,...(probe?{'X-Semasa-Probe':'latency-v1'}:{})},body:JSON.stringify(payload)});
const response=await handler(request(update('/menu')));
assert.equal(response.status,200);
const body=await response.json();
assert.equal(body.method,'sendMessage','menu must be delivered immediately, not typing while GitHub starts');
assert.ok(body.reply_markup?.inline_keyboard?.length,'menu buttons remain available');
assert.equal(writes.at(-1).status,'done','fast commands must not wake the GitHub worker');
console.log('telegram webhook: menu bypasses worker: ok');

writes=[];
assert.equal((await handler(request(update('/menu'),'wrong-signature'))).status,403);
assert.equal(writes.length,0,'unauthenticated requests cannot write inbox rows');
let reply=await (await handler(request(update('/menu',999)))).json();
assert.match(reply.text,/peribadi/);
assert.equal(writes.at(-1).status,'skipped');

for (const mode of ['pending','busy']) {
  pending=mode==='pending'?'poster':null;
  busy=mode==='busy';
  writes=[];
  reply=await (await handler(request(update('/menu')))).json();
  assert.equal(reply.method,'sendChatAction');
  assert.equal(writes.at(-1).status,'new',`${mode} must retain worker ordering`);
}
pending=null;busy=false;
for (const payload of [update('/draf'),{update_id:101,callback_query:{id:'cq',from:{id:111},data:'ok:post-1',message:{message_id:6,chat:{id:111,type:'private'}}}}]) {
  writes=[];
  await handler(request(payload));
  assert.equal(writes.at(-1).status,'new','previews and approvals must remain with the compliance worker');
  assert.deepEqual(writes.at(-1).payload,payload);
}
duplicate=true;
reply=await (await handler(request(update('/menu')))).json();
assert.deepEqual(reply,{ok:true},'duplicate deliveries must not repeat a command response');
console.log('telegram webhook: auth, ordering, approval gates and dedupe: ok');

duplicate=false;
for (const mode of ['pending','busy']) {
  pending=mode==='pending'?'poster':null;
  busy=mode==='busy';
  writes=[];
  const probeReply=await (await handler(request(update('/menu'),'test-signature',true))).json();
  assert.equal(probeReply.probe,true);
  assert.equal(probeReply.inline,false);
  assert.equal(writes.length,0,'a latency probe must not queue work or clear the owner topic');
}
pending=null;busy=false;writes=[];
await handler(request(update('/start AB12CD34'),'test-signature',true));
assert.equal(writes.length,0,'probe mode must not link accounts or run any unsupported command');
console.log('telegram webhook: probe fallback cannot mutate or dispatch: ok');

// ---- 16 Nov 2026: the button menu (menu.js, rules/telegram_menu.json). A tap that only opens another menu is redrawn here, in
// place, without the worker; a read button is answered here; anything a button does, and every tap while something waits, is
// still the worker's, in order.
const tapOf=(data,from=111,id=200)=>({update_id:id,callback_query:{id:'cq2',from:{id:from},data,message:{message_id:9,chat:{id:from,type:'private'}}}});
pending=null;busy=false;duplicate=false;writes=[];
reply=await (await handler(request(tapOf('m:s:content')))).json();
assert.equal(reply.method,'editMessageText','another menu opens at once, in the same message');
assert.equal(reply.message_id,9);
assert.ok(reply.text.startsWith('📰 Kandungan'));
assert.ok(reply.reply_markup.inline_keyboard.flat().some(b=>b.callback_data==='m:home'),'with its way back');
assert.equal(writes.at(-1).status,'done','a menu tap answered here must not wake the GitHub worker');
assert.equal(writes.at(-1).note,'answered (menu: s:content)');
assert.equal(writes.at(-1).payload.semasa_timing.path,'menu');
writes=[];
reply=await (await handler(request(tapOf('a:help')))).json();
assert.equal(reply.method,'sendMessage');
assert.match(reply.text,/\/draf/);
assert.deepEqual(reply.reply_markup.inline_keyboard.flat().map(b=>b.callback_data),['n:home']);
assert.equal(writes.at(-1).note,'answered (menu read: help)');
writes=[];
reply=await (await handler(request(tapOf('n:home')))).json();
assert.equal(reply.method,'sendMessage','the way back under an answer is a new message: the answer stays in the chat');
assert.ok(reply.text.startsWith('Hai Wan'));
assert.equal(writes.at(-1).status,'done');
for (const data of ['a:draf','a:draf_l','a:idea_l','a:poster','a:lk:poster:neon','m:lang:en','a:status']) {
  // a:status needs the database's rows: this stand-in has none to give, so it falls back to the worker like any failed read
  writes=[];
  reply=await (await handler(request(tapOf(data)))).json();
  assert.equal(reply.method,'answerCallbackQuery',`${data} is the worker's`);
  assert.equal(writes.at(-1).status,'new');
  assert.deepEqual(writes.at(-1).payload,tapOf(data));
}
for (const mode of ['pending','busy']) {
  pending=mode==='pending'?'cat:idea:linkedin':null;
  busy=mode==='busy';
  writes=[];
  reply=await (await handler(request(tapOf('m:home')))).json();
  assert.equal(reply.method,'answerCallbackQuery',`${mode}: the worker draws the menu, after what is waiting`);
  assert.equal(writes.at(-1).status,'new');
}
pending=null;busy=false;writes=[];
reply=await (await handler(request(tapOf('m:home',999)))).json();
assert.equal(reply.show_alert,true,'a stranger gets no menu');
assert.equal(writes.at(-1).status,'skipped');
duplicate=true;
reply=await (await handler(request(tapOf('m:home')))).json();
assert.deepEqual(reply,{ok:true},'a tap delivered twice is drawn once');
duplicate=false;
console.log('telegram webhook: menu taps redraw here, actions and ordering stay with the worker: ok');
