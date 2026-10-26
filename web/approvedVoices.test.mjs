import assert from 'node:assert/strict';
import {motionDefaults, motionRow, motionFromIdea, motionFromPost, resolveLanguageVoice, withDefaults} from './src/lib/motion.js';
assert.equal(motionDefaults(null).voice, 'male');
for (const language of ['en','bm','both']) {
  assert.equal(motionRow({brief:'Test',language}).row.voice,'male');
  assert.equal(motionFromIdea({id:'i',source_title:'Test'},'u',null,language).voice,'male');
  assert.equal(motionFromPost({text:{en:{linkedin:'Test'}}},'u',null,language).voice,'male');
  assert.equal(resolveLanguageVoice(language,'female').voice,'female');
}
assert.equal(resolveLanguageVoice('en','kitten').voice,'kitten');
assert.equal(resolveLanguageVoice('bm','kitten').voice,'male');
assert.equal(withDefaults({}, {language:'en',voice:'female'}).defaults.voice,'female');
assert.equal(motionDefaults({motion:{defaults:{voice:'off'}}}).voice,'off');
console.log('Approved voice defaults and explicit overrides pass');
