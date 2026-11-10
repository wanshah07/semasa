/* Stills of a film's scenes, for the storyboard preview (motion_remotion.preview). One bundle, one still per frame asked for:
   node preview.mjs <props.json> <public dir> <out dir> <frame,frame,...> [browser] */
import fs from "node:fs";
import path from "node:path";
import { bundle } from "@remotion/bundler";
import { renderStill, selectComposition } from "@remotion/renderer";

const [propsFile, publicDir, outDir, frames, browser] = process.argv.slice(2);
const inputProps = JSON.parse(fs.readFileSync(propsFile, "utf8"));
const browserExecutable = browser || null;
fs.mkdirSync(outDir, { recursive: true });
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.jsx"), publicDir: path.resolve(publicDir) });
const composition = await selectComposition({ serveUrl, id: "Film", inputProps, browserExecutable, logLevel: "error" });
const list = frames.split(",").map(Number);
for (let i = 0; i < list.length; i++) {
  await renderStill({ composition, serveUrl, output: path.join(outDir, `f${i}.png`), frame: list[i], inputProps, browserExecutable, logLevel: "error" });
}
console.log("stills", list.length);
