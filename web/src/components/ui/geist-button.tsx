/* The Geist-style button Wan pasted (11 Nov 2026). It is saved under this name because `ui/button.tsx` is already shadcn's
   button, which other pasted components import, and `ui/Button.jsx` is Semasa's own. Its colours were fixed hex values
   with `dark:` variants; Semasa has many themes and no `.dark` class, so they read the theme's tokens instead and stay
   readable on every theme. */
import React from "react";
import { Spinner } from "@/components/ui/spinner";

const sizes = [
  { tiny: "px-1.5 h-6 text-sm", small: "px-1.5 h-8 text-sm", medium: "px-2.5 h-10 text-sm", large: "px-3.5 h-12 text-base" },
  { tiny: "w-6 h-6 text-sm", small: "w-8 h-8 text-sm", medium: "w-10 h-10 text-sm", large: "w-12 h-12 text-base" },
];

const types = {
  primary: "bg-ink text-bg fill-bg hover:opacity-85",
  secondary: "bg-surface text-ink fill-ink border border-line hover:bg-surface-2",
  tertiary: "bg-transparent text-ink fill-ink hover:bg-surface-2",
  error: "bg-danger text-white fill-white hover:opacity-90",
  warning: "bg-queue text-black fill-black hover:opacity-90",
};

const shapes = {
  square: { tiny: "rounded", small: "rounded-md", medium: "rounded-md", large: "rounded-lg" },
  circle: { tiny: "rounded-full", small: "rounded-full", medium: "rounded-full", large: "rounded-full" },
  rounded: { tiny: "rounded-[100px]", small: "rounded-[100px]", medium: "rounded-[100px]", large: "rounded-[100px]" },
};

export interface GeistButtonProps extends Omit<React.ButtonHTMLAttributes<HTMLButtonElement>, "type" | "prefix"> {
  size?: keyof (typeof sizes)[0];
  type?: keyof typeof types;
  shape?: keyof typeof shapes;
  svgOnly?: boolean;
  prefix?: React.ReactNode;
  suffix?: React.ReactNode;
  shadow?: boolean;
  loading?: boolean;
  fullWidth?: boolean;
  /** The native button type. The pasted component always submitted the form it sat in; Semasa defaults to "button". */
  htmlType?: "button" | "submit" | "reset";
}

export const GeistButton = React.forwardRef<HTMLButtonElement, GeistButtonProps>(function GeistButton(
  { size = "medium", type = "primary", shape = "square", svgOnly = false, children, prefix, suffix, shadow = false,
    loading = false, disabled = false, fullWidth = false, htmlType = "button", className = "", ...rest }, ref) {
  const off = disabled || loading;
  return (
    <button
      ref={ref}
      type={htmlType}
      disabled={off}
      aria-busy={loading || undefined}
      className={`flex items-center justify-center gap-0.5 duration-150 focus-visible:outline focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-accent ${sizes[+svgOnly][size]} ${off ? "cursor-not-allowed border border-line bg-surface-2 text-muted fill-muted" : types[type]} ${shapes[shape][size]}${shadow ? " shadow-card" : ""}${fullWidth ? " w-full" : ""} ${className}`}
      {...rest}
    >
      {loading ? <Spinner size={size === "large" ? 24 : 16} /> : prefix}
      {svgOnly ? children : (
        <span className={`overflow-hidden text-ellipsis whitespace-nowrap font-sans${size === "tiny" ? "" : " px-1.5"}`}>{children}</span>
      )}
      {!loading && suffix}
    </button>
  );
});

export default GeistButton;
