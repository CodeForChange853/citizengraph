/** Placeholder app mark: a plain blue rounded square with a monogram. Not a seal, flag or mascot. */
export function Monogram({ className = "size-9" }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={`inline-flex shrink-0 items-center justify-center rounded-md bg-primary-bg text-body font-bold text-on-primary ${className}`}
    >
      CG
    </span>
  );
}
