// A Wanshah robot as a real 3D robot: boxes in CSS 3D (preserve-3d, no library), turning slowly side to side so every
// face shows. Head with a visor, antenna, torso with the W1/W2/W3 badge and two arms. The antenna and eyes glow while
// active; off, everything goes grey. Motion stops for visitors who ask for reduced motion (a fixed three-quarter view).
// Ported from halal-executive src/components/Robot3D.jsx (Wan, 23 Oct 2026); the classes are in index.css (r3-*).
import { THEMES, shadeFor, glassFor, METAL, GREY, GREY_GLASS } from "../lib/robots";

// One box centred on (x, y, z): six faces; `front` may carry content.
function Box({ w, h, d, x = 0, y = 0, z = 0, shade, radius = 0, children, className = "", style }) {
  const f = (name, fw, fh, tf, kids) => (
    <div key={name} className="r3-face" style={{ width: fw, height: fh, marginLeft: -fw / 2, marginTop: -fh / 2, transform: tf, background: shade[name], borderRadius: radius }}>{kids}</div>
  );
  return (
    <div className={`r3-box ${className}`} style={{ transform: `translate3d(${x}px,${y}px,${z}px)`, ...style }}>
      {f("front", w, h, `translateZ(${d / 2}px)`, children)}
      {f("back", w, h, `rotateY(180deg) translateZ(${d / 2}px)`)}
      {f("right", d, h, `rotateY(90deg) translateZ(${w / 2}px)`)}
      {f("left", d, h, `rotateY(-90deg) translateZ(${w / 2}px)`)}
      {f("top", w, d, `rotateX(90deg) translateZ(${h / 2}px)`)}
      {f("bottom", w, d, `rotateX(-90deg) translateZ(${h / 2}px)`)}
    </div>
  );
}

export default function Robot3D({ tone = "kios", state = "standby", size = 140, label, name }) {
  const t = THEMES[tone] || THEMES.guest;
  const on = state === "active", off = state === "offline";
  const body = off ? GREY : shadeFor(t.shell), metal = off ? GREY : METAL;
  const eye = off ? "#4b5563" : t.eye, glow = off ? "#6b7280" : t.glow;
  const glass = off ? GREY_GLASS : glassFor(t.visor);
  const badge = label || t.label;
  const who = name || t.name;
  const k = size / 160;
  return (
    <div className={`r3-scene ${off ? "r3-off" : ""}`} style={{ width: size, height: size * 1.125 }} role="img" aria-label={`${who} 3D robot, ${state}`}>
      <div className="r3-stage" style={{ transform: `scale(${k})` }}>
        <div className="r3-shadow" />
        <div className="r3-rig">
          <div className="r3-bob">
            {/* antenna: a stem and a ball made of two crossed discs */}
            <Box w={4} h={18} d={4} y={-96} shade={metal} />
            <div className="r3-box" style={{ transform: "translate3d(0,-110px,0)" }}>
              {[0, 90].map((a) => <div key={a} className={`r3-disc ${on ? "r3-pulse" : ""}`} style={{ transform: `rotateY(${a}deg)`, background: `radial-gradient(circle at 35% 30%,#fff,${glow} 55%,${off ? "#4b5563" : t.shell[1]})` }} />)}
            </div>
            {/* head */}
            <Box w={92} h={68} d={68} y={-56} shade={body} radius={14}>
              <div className="r3-visor" style={{ background: glass }}>
                <i className={`r3-eye ${off ? "r3-eye-off" : "r3-blink"}`} style={{ background: eye, boxShadow: on ? `0 0 10px ${glow}` : "none" }} />
                <i className={`r3-eye ${off ? "r3-eye-off" : "r3-blink"}`} style={{ background: eye, boxShadow: on ? `0 0 10px ${glow}` : "none" }} />
              </div>
            </Box>
            <Box w={10} h={24} d={18} x={-52} y={-56} shade={metal} />
            <Box w={10} h={24} d={18} x={52} y={-56} shade={metal} />
            {/* neck and torso */}
            <Box w={22} h={10} d={22} y={-16} shade={metal} />
            <Box w={78} h={62} d={48} y={22} shade={body} radius={10}>
              <div className="r3-badge" style={{ color: eye, background: glass }}>{badge}<b className={on ? "r3-pulse" : ""} style={{ background: glow }} /></div>
            </Box>
            {/* arms */}
            <Box w={14} h={48} d={16} x={-52} y={22} shade={metal} radius={6} className="r3-arm-l" />
            <Box w={14} h={48} d={16} x={52} y={22} shade={metal} radius={6} />
          </div>
        </div>
      </div>
    </div>
  );
}
