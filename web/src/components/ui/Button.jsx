const styles = {
  primary: "bg-accent text-accent-ink hover:brightness-110 shadow-card",
  ghost: "bg-transparent text-ink hover:bg-surface-2 border border-line",
  soft: "bg-surface-2 text-ink hover:bg-line/60",
  danger: "bg-danger/10 text-danger hover:bg-danger/20",
};

export default function Button({ variant = "primary", size = "md", className = "", children, ...rest }) {
  const pad = size === "sm" ? "px-3 py-1.5 text-xs" : size === "lg" ? "px-6 py-3 text-base" : "px-4 py-2 text-sm";
  return (
    <button
      className={`inline-flex items-center gap-2 rounded-pill font-medium transition duration-200 ease-out
        disabled:opacity-50 disabled:cursor-not-allowed ${styles[variant]} ${pad} ${className}`}
      {...rest}
    >
      {children}
    </button>
  );
}
