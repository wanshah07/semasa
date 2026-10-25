import assert from 'node:assert/strict';
import { motionRow, motionFromIdea, motionFromPost, motionDefaults, withDefaults } from './src/lib/motion.js';
for (const language of ['en', 'bm', 'both']) {
  const expected = language === 'en' ? 'kitten' : 'female';
  assert.equal(motionRow({brief:'x', language}).row.voice, expected);
  assert.equal(motionFromIdea({id:'i',source_title:'x'}, null, null, language).voice, expected);
  assert.equal(motionFromPost({id:'p',text:{en:{facebook:'x'}}}, null, null, language).voice, expected);
}
const defaults = withDefaults({}, {design:'continuous-line', language:'bm', voice:'kitten'}).defaults;
assert.equal(defaults.voice, 'female');
assert.equal(motionDefaults({motion:{defaults}}).design, 'continuous-line');
for (const row of [motionRow({brief:'x',design:'continuous-line'}).row,
  motionFromIdea({id:'i',source_title:'x'},null,defaults),
  motionFromPost({id:'p',text:{en:{facebook:'x'}}},null,defaults)]) {
  assert.equal(row.options.design, 'continuous-line');
}
assert.equal(motionRow({brief:'x'}).row.options.design, 'bright-editorial');
const idea = {id:'url',source_url:'https://example.com/paper', reference_urls:['https://example.com/ref'],
  source_name:'Journal',angle:'mechanism',domain:'cosmetics',citations:[{doi:'10.1/example'}],source_summary:'x'.repeat(4000)};
const row = motionFromIdea(idea);
assert.ok(row);
assert.equal(row.options.evidence.source_name, 'Journal');
assert.deepEqual(row.options.evidence.reference_urls, idea.reference_urls);
assert.deepEqual(row.options.evidence.citations, idea.citations);
assert.equal(row.options.evidence.source_summary.length, 4000);
assert.equal(motionFromPost({text:{bm:{facebook:'BM only'}}}).brief, 'BM only');
const { motionVariantMatches } = await import('./src/lib/motion.js');
const wanted = motionFromIdea({id:'i',source_title:'x'});
assert.equal(motionVariantMatches({...wanted,status:'error'}, wanted), false);
assert.equal(motionVariantMatches({...wanted,status:'done'}, wanted), true);
assert.equal(motionVariantMatches({...wanted,language:'bm'}, wanted), false);
assert.equal(motionVariantMatches({...wanted,options:{...wanted.options,design:'continuous-line'}}, wanted), false);
assert.deepEqual(wanted.options.preferred_preview_music, {source:'user-reel',rights_status:'unverified',preview_only:true});
console.log('motionRequirements.test.mjs: ok');
