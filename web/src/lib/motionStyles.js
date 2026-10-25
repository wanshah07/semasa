import recipes from '../../../rules/motion/recipes.json' with { type: 'json' };
export const catalog = recipes;
export const designOptions = [
  {id:'bright-editorial', name:'Design 1 · Original Bright Photo / Diagram / Editorial'},
  {id:'continuous-line', name:'Design 2 · Continuous Line (approved v17)'},
];
const bright = { ...recipes[3], id: 'bright-education', name: 'Bright education (Financial Education motifs)' };
const supported = new Set(['auto', 'bright-education', 'financial-education-reel']);
// Actual current assets: an idea/link and optional AI backdrop, not uploaded product/footage/captures.
export const recipeOf = (id) => catalog.find(r => r.id === id && supported.has(id)) || bright;
export function recipeOptions() {
  return [{ id: 'auto', name: 'Auto · suitable educational adaptation' }, bright, ...catalog].map(r => ({
    ...r, available: supported.has(r.id),
    reason: r.duplicate_of ? 'Source duplicates Tutorial / Screen Recording; no testimonial recipe supplied' :
      supported.has(r.id) ? '' : 'Needs uploaded assets not yet supported by this form',
  }));
}
export const styleOf = (id) => supported.has(id) ? id : 'bright-education';
