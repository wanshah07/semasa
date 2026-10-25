import assert from 'node:assert/strict';
import {uploadMotionAsset,removeMotionAssets,MOTION_ASSET_BUCKET} from './src/lib/motionAssetStorage.js';
const calls=[];
const client={storage:{from:bucket=>({
  upload:async(path,file,options)=>{calls.push({bucket,path,file,options});return {error:null};},
  remove:async paths=>{calls.push({bucket,paths});return {error:null};}
})}};
const file={name:'original.png',type:'image/png',size:12};
const metadata={role:'screenshot',source:'Local test fixture only',rights:'self-owned',attribution:'test'};
await assert.rejects(()=>uploadMotionAsset(client,null,file,metadata),/rights/);
await assert.rejects(()=>uploadMotionAsset(client,{id:'owner'},{...file,type:'image/svg+xml'},metadata),/MIME/);
await assert.rejects(()=>uploadMotionAsset(client,{id:'owner'},file,{...metadata,source:''}),/source/);
assert.equal(calls.length,0);
const ref=await uploadMotionAsset(client,{id:'owner'},file,metadata);
assert.equal(calls[0].bucket,MOTION_ASSET_BUCKET);
assert.ok(ref.path.startsWith('owner/'));
assert.ok(ref.path.endsWith('-original.png'));
assert.equal(ref.mime,'image/png');
assert.equal(calls[0].options.upsert,false);
assert.equal(calls[0].options.contentType,'image/png');
assert.equal(ref.rights,'self-owned');
assert.equal('url' in ref,false);
await removeMotionAssets(client,[ref]);
assert.deepEqual(calls[1].paths,[ref.path]);
const denied={storage:{from:()=>({upload:async()=>({error:{message:'private bucket unavailable'}})})}};
await assert.rejects(()=>uploadMotionAsset(denied,{id:'owner'},file,metadata),/private bucket unavailable/);
const removeDenied={storage:{from:()=>({remove:async()=>({error:{message:'delete denied'}})})}};
await assert.rejects(()=>removeMotionAssets(removeDenied,[ref]),/delete denied/);
console.log('motion asset storage: private paths, validation, rights, upload and errors passed (isolated storage double; no live upload)');
