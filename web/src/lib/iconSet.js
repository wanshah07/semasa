/* The icon set is a decision, not an import default (anti-slop R-04, finding 3, Wan 26 Oct 2026: "fix 3 and 4").
   Glyphs stay Lucide's: they are the relevant ones for each button and tab, and redrawing 56 files of them would change nothing a
   user reads. What makes the set Semasa's is how it is drawn, set once here for every icon in the page:
     - a 1.5 stroke instead of the library's default 2: lighter, to sit beside 14 to 16px body text rather than over it;
     - square line ends and mitred corners (the `semasa-icon` class, index.css): the strokes of a technical drawing or a lab
       instrument label, which is the register of a regulatory tool, not the rounded friendliness of a consumer app.
   An icon that needs its own weight still passes `strokeWidth` itself (the sidebar does) and wins over this.
   To go back to the library look: delete the ICON_SET spread in main.jsx. */
export const ICON_SET = { strokeWidth: 1.5, className: "semasa-icon" };
