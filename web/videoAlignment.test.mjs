import assert from 'node:assert/strict';
import {motionRow,motionDefaults,motionFromIdea,motionFromPost,motionVariantMatches,withDefaults} from './src/lib/motion.js';
import {resolveFormat,VIDEO_POLICY} from './src/lib/videoFormatPolicy.js';
for (const format of ['english-voiced','malay-voiced','silent-first','gimmick']) {
  const d = motionDefaults({motion:withDefaults({}, {format,seconds:60})});
  for (const row of [motionRow({brief:'Test',...d}).row,motionFromIdea({id:'i',source_title:'Test'},'u',d),motionFromPost({text:{en:{linkedin:'Test'}}},'u',d)]) {
    assert.equal(row.options.format,format);
    assert.equal(row.seconds,format === 'gimmick' ? 10 : 60);
    assert.equal(row.voice,format === 'silent-first' ? 'off' : 'male');
  }
}
assert.equal(resolveFormat({mode:'teaser',seconds:60}).seconds,10);
assert.equal(resolveFormat({voice:'female',language:'bm'}).voice,'female');
assert.equal(resolveFormat({voice:'off'}).format,'silent-first');
assert.equal(VIDEO_POLICY.voices.en.id,'en-SG-WayneNeural');
assert.equal(VIDEO_POLICY.voices.bm.id,'ms-MY-OsmanNeural');
const normal=motionFromIdea({id:'i',source_title:'Test'});
assert.equal(motionVariantMatches({...normal,status:'done',options:{...normal.options,mute_all:true}},normal),false);
assert.equal(motionVariantMatches({...normal,status:'done',options:{...normal.options,personal_avatar:{path:'u/x.png'}}},normal),false);
const personal=motionFromIdea({source_title:'Test',stream:'linkedin'},'u',{language:'bm',resolution:'square'});
assert.equal(personal.language,'en');assert.equal(personal.resolution,'portrait');
assert.equal(personal.options.brand_profile,'linkedin-personal');
const policyHelpers = await import('./src/lib/videoFormatPolicy.js');
assert.equal(policyHelpers.selectFormat({voice:'off'},'english-voiced').voice,'male');
assert.equal(policyHelpers.selectFormat({voice:'female'},'malay-voiced').voice,'female');
assert.equal(policyHelpers.selectFormat({voice:'male'},'silent-first').voice,'off');
console.log('Video alignment: formats, entrypoints, variants, personal policy pass');
