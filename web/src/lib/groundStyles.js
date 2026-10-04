/* Background styles to start from when the AI makes a background (Design tab → Background → "AI picture"). Each is a prompt written the
   way an image generator wants it: the subject, WHERE it sits, the palette, the light, and which part stays empty for words. The first
   one is the pink glass sphere of the event poster Wan used as a reference (4 Oct 2026). A light picture gets dark ink and no scrim on
   its own (lib/cards/studio.js groundIsLight), so these suit the Event poster and every ERA/Grid design. */
export const GROUND_STYLES = [
  { k: "glass", bm: "Sfera kaca merah jambu", en: "Pink glass sphere",
    prompt: "Soft pastel product photography: a large translucent pink glass sphere filled with clear gel bubbles and droplets, cropped off the bottom-right corner and filling about a third of the frame, glossy refractions, shallow depth of field, on a pale blush-lilac to white studio gradient. The left half and the top stay empty, smooth and airy." },
  { k: "gel", bm: "Titisan gel jernih", en: "Clear gel droplets",
    prompt: "Macro photography of clear glossy gel droplets and bubbles on a pale lilac-to-white surface, soft diffused light, droplets gathered along the right edge and bottom, the rest of the frame smooth, empty and bright." },
  { k: "studio", bm: "Kecerunan studio lembut", en: "Soft studio gradient",
    prompt: "A seamless studio backdrop, smooth gradient from pale blush pink (#F4E3EA) at the top left to soft lilac (#D9D0E6) at the bottom right, gentle vignette, subtle paper grain, nothing else in the frame." },
  { k: "lab", bm: "Makmal bersih, cerah", en: "Bright clean lab",
    prompt: "A bright, clean cosmetics laboratory bench seen from a low angle, soft daylight, white and pale teal tones, glassware slightly out of focus on the right third, the left two thirds calm and empty." },
  { k: "botanical", bm: "Daun & embun", en: "Leaves and dew",
    prompt: "Soft-focus green leaves with dew drops along the right edge on a pale cream background, natural morning light, the left side and the centre smooth and empty." },
];

/** What every generated background must also say, whichever starter or free text it began from. */
export const GROUND_SUFFIX = " A calm background for text: no words, no letters, no logos, no products, no people's faces.";
