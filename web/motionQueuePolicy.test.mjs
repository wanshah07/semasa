import assert from 'node:assert/strict';
import { motionFromIdea, motionFromPost, motionRow, formOf, startFields, motionVariantMatches } from './src/lib/motion.js';
const avatar = {path:'owner/personal.png', rights:'owned'};
for (const make of [d => motionFromIdea({id:'i',source_title:'Evidence'}, 'u', d),
  d => motionFromPost({idea_id:'i',text:{en:{facebook:'Evidence'}}}, 'u', d)]) {
  for (const config of [
    {format:'silent-first',voice:'off',muteAll:true},
    {format:'gimmick',mode:'teaser',seconds:10,voice:'female'},
    {format:'malay-voiced',language:'both',voice:'male'},
  ]) {
    const row = make({...config,personalAvatar:avatar,design:'continuous-line'});
    assert.equal(row.status, 'waiting');
    const form = formOf(row);
    assert.equal(form.format, row.options.format);
    assert.equal(form.muteAll, row.options.mute_all);
    assert.deepEqual(form.personalAvatar, avatar);
    const started = startFields(row, form);
    assert.equal(started.status,'pending');
    assert.equal(started.options.format,row.options.format);
    assert.equal(started.voice,row.voice);
    assert.equal(started.options.mute_all,row.options.mute_all);
    assert.deepEqual(started.options.personal_avatar,avatar);
    assert.deepEqual(started.options.evidence,row.options.evidence);
    assert.equal(started.options.design,'continuous-line');
    assert.equal(motionVariantMatches({...row,options:{...row.options,design:'bright-editorial'}},row),true);
    assert.equal(motionVariantMatches({...row,status:'done',options:{...row.options,mute_all:!row.options.mute_all}},row),false);
  }
}
assert.equal(motionRow({brief:'Direct form'}).row.status,'pending');
const personal = motionFromIdea({id:'p',source_title:'Personal',stream:'linkedin'},'u',{language:'bm',format:'malay-voiced',personalAvatar:avatar});
const started = startFields(personal, formOf(personal));
assert.equal(started.language,'en');
assert.equal(started.resolution,'portrait');
assert.equal(started.options.brand_profile,'linkedin-personal');
assert.equal(startFields(personal,{...formOf(personal),voice:'female'}).voice,'female');
console.log('motionQueuePolicy.test.mjs: ok');
