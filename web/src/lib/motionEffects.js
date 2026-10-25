import library from '../../../rules/motion/style-effects.json' with {type:'json'};
import sections from '../../../rules/motion/effect-sections.json' with {type:'json'};
import adapters from '../../../rules/motion/effect-adapters.json' with {type:'json'};
export const effectPolicy = adapters;
const byId = Object.fromEntries(library.effects.map(e=>[e.id,e]));
export const validEffects = ids => [...new Set((Array.isArray(ids) ? ids : ['B04']).filter(id=>byId[id]))];
export function effectGroups(query='') {
  const q=query.trim().toLowerCase();
  return sections.groups.map(g=>({...g,effects:g.ids.map((id,i)=>({...byId[id],occurrence:g.occurrences[i],...adapters[id]})).filter(e=>!q || `${g.title} ${e.id} ${e.name} ${e.description}`.toLowerCase().includes(q))})).filter(g=>g.effects.length);
}
/** Conservative recipe: one visual plus optional pace, never every catalog entry. Mirrors worker selection. */
export function recommendedEffects({brief='', mode='explainer', assets=[]}={}) {
  const screenshot=assets.some(a=>a.mime?.startsWith('image/') && a.role==='screenshot' && a.source?.trim());
  const visual=screenshot ? 'P01' : /\b(abstract|calm|ambient)\b/i.test(brief) ? 'B08' : 'B04';
  return mode==='teaser' ? [visual] : [visual,'M03'];
}
export const resolveEffects = d => d.effectMode==='manual' ? validEffects(d.effects) : recommendedEffects(d);
export const toggleEffect = (ids,id) => validEffects(ids.includes(id) ? ids.filter(v=>v!==id) : [...ids,id]);
export const assetModeOf = v => ['manual','mixed'].includes(v) ? v : 'auto';
export const ASSET_TYPES = {'image/png':'.png','image/jpeg':'.jpg','image/webp':'.webp','video/mp4':'.mp4','audio/mpeg':'.mp3','audio/wav':'.wav','application/pdf':'.pdf','text/plain':'.txt'};
export function assetRefusal(file) {
  if (!ASSET_TYPES[file.type] || !file.name.toLowerCase().endsWith(ASSET_TYPES[file.type])) return 'Unsupported MIME or file extension';
  if (!/^[A-Za-z0-9][A-Za-z0-9_. -]{0,100}$/.test(file.name) || file.name.includes('..')) return 'Unsafe filename';
  if (!(file.size>0 && file.size<=20*1024*1024)) return 'Choose a non-empty file up to 20 MB';
  return '';
}
