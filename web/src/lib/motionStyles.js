import recipes from '../../../rules/motion/recipes.json' with { type: 'json' };
import bundles from '../../../rules/motion/style-bundles.json' with { type: 'json' };
// Keep the old eight-section attachment distinct from NEW Styles' complete native adaptations.
export const catalog = recipes;
export const completeRecipes = bundles;
export const designOptions = [
  {id:'bright-editorial', name:'Design 1 · Original Bright Photo / Diagram / Editorial'},
  {id:'continuous-line', name:'Design 2 · Continuous Line (approved v17)'},
];
const bright = { ...recipes[3], id: 'bright-education', name: 'Bright education (Financial Education motifs)' };
const supported = new Set(['auto', 'bright-education', 'financial-education-reel',
  ...bundles.filter(r => r.kind === 'native-motion' && !r.required_assets.length).map(r => r.id)]);
// Idea/source inputs support native illustrations, NOT uploaded footage/captures/mattes.
export const recipeOf = (id) => [...catalog, ...bundles].find(r => r.id === id && supported.has(id)) || bright;
export function recipeOptions() {
  return [{ id: 'auto', name: 'Auto · suitable educational adaptation' }, bright, ...bundles, ...catalog].map(r => ({
    ...r, available: supported.has(r.id),
    reason: r.duplicate_of ? 'Source duplicates Tutorial / Screen Recording; no testimonial recipe supplied' :
      r.kind === 'uploaded-footage' ? 'Uploaded-footage editing unavailable; needs original video, real captures and timing' :
      supported.has(r.id) ? '' : 'Needs uploaded assets not yet supported by this form',
  }));
}
export const styleOf = (id) => supported.has(id) ? id : 'bright-education';
