import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
const url = new URL('../supabase/functions/semasa-telegram/fast.js', import.meta.url);
assert.ok(existsSync(url), 'A bounded fast-model runner is required');
const { tryFastGates } = await import(url);
let clock = 1000;
const calls = [];
const tries = [{name:'First',model:'one',gate:{}},{name:'Backup',model:'two',gate:{}}];
const answer = await tryFastGates(tries, {
  deadline:16000, now:()=>clock,
  messagesFor:()=>[], requestFor:()=>({url:'https://model.example/v1/chat',headers:{},body:'{}'}),
  answerText:(_gate,j)=>j?.answer, errorText:()=>'', switchable:()=>true,
  fetchImpl:async (_url, options)=> {
    calls.push(options);
    if (calls.length===1) { clock+=7000; throw new DOMException('timed out','TimeoutError'); }
    return {ok:true,json:async()=>({answer:'OK',model:'two-live'})};
  },
});
assert.equal(calls.length,2,'a slow first model must leave a chance for the backup');
assert.equal(answer.answer,'OK');
assert.equal(answer.who,'Backup · two-live');
assert.equal(answer.attempts,2);
console.log('telegram latency: backup after a slow first model: ok');

const late = await tryFastGates(tries.slice(0,1), {
  deadline:16000, now:()=>clock, messagesFor:()=>[], requestFor:()=>({url:'https://model.example',body:'{}'}),
  answerText:(_g,j)=>j.answer,errorText:()=>'',switchable:()=>true,
  fetchImpl:async()=>({ok:true,json:async()=>{clock=17000;return {answer:'late'};}}),
});
assert.equal(late,null,'late JSON must not escape the overall webhook model deadline');
console.log('telegram latency: total deadline includes response body: ok');

let refusedCalls=0;
const common={deadline:16000,now:()=>1000,messagesFor:()=>[],requestFor:()=>({url:'https://model.example',body:'{}'}),answerText:(_g,j)=>j?.answer,errorText:()=>'',switchable:()=>false};
assert.equal(await tryFastGates(tries,{...common,fetchImpl:async()=>{refusedCalls++;return {ok:false,status:400,json:async()=>({error:{message:'content refused'}})};}}),null);
assert.equal(refusedCalls,1,'a content refusal must not be routed around');
assert.equal(await tryFastGates(tries,{...common,now:()=>16000,fetchImpl:async()=>{throw new Error('expired budget made a call');}}),null);
console.log('telegram latency: refusal and expired-budget gates: ok');
