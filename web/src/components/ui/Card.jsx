export default function Card({ as: Tag = "div", className = "", children, ...rest }) {
  return (
    <Tag className={`bg-surface border border-line/80 rounded-card shadow-card ${className}`} {...rest}>
      {children}
    </Tag>
  );
}
