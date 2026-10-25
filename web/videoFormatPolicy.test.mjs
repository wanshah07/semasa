import assert from 'node:assert/strict';
import {motionRow, motionFromIdea, motionFromPost, motionDefaults, withDefaults, motionVariantMatches} from './src/lib/motion.js';
const factories = [d => motionRow({brief:'test', ...d}).row,
  d => motionFromIdea({id:'i', source_title:'test'}, null, d),
  d => motionFromPost({id:'p', text:{en:{facebook:'test'}}}, null, d)];
for (const make of factories) {
  for (const [format, language, voice, seconds] of [['english-voiced','en','kitten',30], ['malay-voiced','bm','female',30], ['silent-first','en','off',30], ['gimmick','en','kitten',10]]) {
    const row = make({format, seconds:60});
    assert.equal(row.options.format, format);
    assert.equal(row.language, language);
    assert.equal(row.voice, voice);
    assert.equal(row.seconds, format === 'gimmick' ? 10 : 60);
    assert.equal(row.options.policy_version, 1);
  }
  const personal = make({stream:'linkedin', language:'bm', resolution:'square'});
  // Ideas/posts carry their own stream; direct form verifies personal override below.
  assert.ok(personal.options.format);
}
const personal = motionRow({brief:'test', stream:'linkedin', language:'bm', resolution:'square'}).row;
assert.equal(personal.language, 'en');
assert.equal(personal.resolution, 'portrait');
assert.equal(personal.options.brand_profile, 'linkedin-personal');
const d = withDefaults({}, {format:'silent-first', seconds:60, muteAll:true}).defaults;
assert.equal(d.format, 'silent-first');
assert.equal(d.voice, 'off');
assert.equal(motionDefaults({motion:{defaults:d}}).muteAll, true);
const row = motionRow({brief:'test', format:'silent-first'}).row;
assert.equal(motionVariantMatches({...row, options:{...row.options, format:'english-voiced'}}, row), false);
assert.equal(motionRow({brief:'test', mode:'teaser', seconds:60}).row.seconds, 10);
console.log('videoFormatPolicy.test.mjs: ok');
