/** The one small header illustration: a checklist sheet. Decorative, uses palette tokens only. */
export function HeaderIllustration() {
  return (
    <svg viewBox="0 0 64 64" aria-hidden="true" focusable="false" className="size-16 shrink-0">
      <rect x="10" y="6" width="38" height="50" rx="6" fill="var(--surface)" stroke="var(--primary)" strokeWidth="3" />
      <path d="M18 20l3 3 6-6" fill="none" stroke="var(--primary)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M18 34l3 3 6-6" fill="none" stroke="var(--primary)" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <path d="M33 21h8M33 35h8M18 46h23" stroke="var(--border-strong)" strokeWidth="3" strokeLinecap="round" />
      <circle cx="48" cy="46" r="11" fill="var(--accent-bg)" stroke="var(--primary)" strokeWidth="3" />
      <path d="M43 46h10M48 41v10" stroke="var(--on-accent)" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
