/* The fonts Kanvas can set text in, and the weights each has (public/cards/fonts.css and fragrance-fonts.css). Pure, so Node tests can read it:
   lib/canvasSeed.js re-exports it but imports the page's translator, which Node cannot load. */
export const FONTS = {
  "Playfair Display": [700, 800], Anton: [400], Poppins: [600, 700, 800], "Instrument Sans": [400, 500, 600],
  "JetBrains Mono": [400, 500], Caveat: [700],
};
