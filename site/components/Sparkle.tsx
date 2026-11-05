export function Sparkle({ className = "", delay = 0, size = 22 }: { className?: string; delay?: number; size?: number }) {
  return (
    <svg
      aria-hidden
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={`sparkle absolute ${className}`}
      style={{ animationDelay: `${delay}s` }}
    >
      <path d="M12 0c.8 6.4 4.8 10.6 12 12-7.2 1.4-11.2 5.6-12 12-.8-6.4-4.8-10.6-12-12C7.2 10.6 11.2 6.4 12 0Z" fill="#F7BE3F" />
    </svg>
  );
}
