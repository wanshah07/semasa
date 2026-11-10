import React from "react";
import { Composition, registerRoot } from "remotion";
import { Film } from "./Film.jsx";

const SAMPLE = {
  width: 1080, height: 1920, fps: 30, seconds: 6,
  palette: { ground: "#e5f6ed", ink: "#143e35", accent: "#287b65", accent2: "#fff7e6" },
  scenes: [{ id: "s1", role: "hook", heading: "Contoh tajuk", lines: ["Baris pertama"], photo: "",
             start: 0, duration: 6, captions: [] }],
  outro: null,
};

const Root = () => (
  <Composition
    id="Film" component={Film} defaultProps={SAMPLE} fps={30} width={1080} height={1920} durationInFrames={180}
    calculateMetadata={({ props }) => ({
      width: props.width, height: props.height, fps: props.fps,
      durationInFrames: Math.max(1, Math.round(props.seconds * props.fps)),
    })}
  />
);

registerRoot(Root);
