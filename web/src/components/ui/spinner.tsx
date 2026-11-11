/* The twelve-bar spinner Wan pasted with the Geist-style button (11 Nov 2026). The original used Next's `<style jsx>`,
   which Vite does not have, so the keyframes are a plain <style> with their own name. */
import React from "react";

interface SpinnerProps {
  size?: number;
  color?: string;
}

const bars = Array.from({ length: 12 }, (_, i) => ({
  animationDelay: `${(-1.2 + i * 0.1).toFixed(1)}s`,
  transform: `rotate(${i === 0 ? 0.0001 : i * 30}deg) translate(146%)`,
}));

export const Spinner = ({ size = 20, color = "rgb(var(--c-muted))" }: SpinnerProps) => {
  return (
    <div style={{ width: size, height: size }} role="status" aria-label="Loading">
      <style>{"@keyframes semasa-spinner { 0% { opacity: 1 } 100% { opacity: 0.15 } }"}</style>
      <div className="relative left-1/2 top-1/2" style={{ width: size, height: size }}>
        {bars.map((item) => (
          <div
            key={item.transform}
            className="absolute -left-[10%] -top-[3.9%] h-[8%] w-[24%] rounded-[5px]"
            style={{ backgroundColor: color, animation: "semasa-spinner 1.2s linear infinite", ...item }}
          />
        ))}
      </div>
    </div>
  );
};

export default Spinner;
