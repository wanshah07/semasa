import { assetRefusal } from './motionEffects.js';
export const MOTION_ASSET_BUCKET = 'semasa-motion-assets';
/** Private refs only: no public URL or credential is put into a job. */
export async function uploadMotionAsset(client, user, file, metadata) {
  const why=assetRefusal(file);
  if (why) throw new Error(why);
  if (!user?.id || !['licensed','self-owned'].includes(metadata.rights)) throw new Error('Confirm asset rights');
  if (metadata.role==='screenshot' && !metadata.source.trim()) throw new Error('Screenshot source is required');
  const name=file.name.replace(/[^A-Za-z0-9_.-]/g,'-');
  const path=`${user.id}/${crypto.randomUUID()}-${name}`;
  const bucket=client.storage.from(MOTION_ASSET_BUCKET);
  const {error}=await bucket.upload(path,file,{contentType:file.type,upsert:false});
  if(error) throw new Error(error.message);
  return {path,mime:file.type,size:file.size,...metadata};
}
export async function removeMotionAssets(client, refs) {
  if(refs.length) {
    const {error}=await client.storage.from(MOTION_ASSET_BUCKET).remove(refs.map(r=>r.path));
    if(error) throw new Error(error.message);
  }
}
