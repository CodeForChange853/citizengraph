// Small stroke icons (24x24). Always decorative: the meaning is in the text next to them.

const PATHS = {
  check: "M5 12.5l4.5 4.5L19 7.5",
  info: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 11v5 M12 8h.01",
  alert: "M12 3.5l9.5 16.5h-19L12 3.5z M12 10v4.5 M12 17.5h.01",
  wifiOff:
    "M3 3l18 18 M2 8.8a15 15 0 0 1 4.2-2.6 M22 8.8a15 15 0 0 0-9.5-3.8 M5.2 12.7a10 10 0 0 1 3.4-2.1 M18.8 12.7a10 10 0 0 0-3.6-2.2 M8.6 16.3a5 5 0 0 1 6.8 0 M12 20h.01",
  clock: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 7v5l3 2",
  banknote:
    "M4 6h16a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2z M12 15a3 3 0 1 0 0-6 3 3 0 0 0 0 6z",
  list: "M9 6h12 M9 12h12 M9 18h12 M4 6h.01 M4 12h.01 M4 18h.01",
  pin: "M12 21s7-6.2 7-11.5a7 7 0 0 0-14 0C5 14.8 12 21 12 21z M12 12a2.5 2.5 0 1 0 0-5 2.5 2.5 0 0 0 0 5z",
  building:
    "M6 21V4a1 1 0 0 1 1-1h10a1 1 0 0 1 1 1v17 M4 21h16 M9.5 8h.01 M14.5 8h.01 M9.5 12h.01 M14.5 12h.01 M10 21v-4h4v4",
  chevronRight: "M9 5l7 7-7 7",
  arrowRight: "M5 12h14 M13 6l6 6-6 6",
  ask: "M4 5h16v11H9.5L4 20.5V5z",
  bookmark: "M6 3.5h12v17.5l-6-4.2L6 21V3.5z",
  help: "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M9.6 9.6a2.5 2.5 0 1 1 3.6 2.2c-.8.5-1.2 1-1.2 1.9 M12 17h.01",
  send: "M4 12l16-8-6 16-3-7-7-1z",
  trash: "M4 7h16 M9.5 7V4h5v3 M6.5 7l1 13h9l1-13",
  business:
    "M4 7h16a1 1 0 0 1 1 1v11a1 1 0 0 1-1 1H4a1 1 0 0 1-1-1V8a1 1 0 0 1 1-1z M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2",
  family:
    "M15.5 20v-1.5a3.5 3.5 0 0 0-3.5-3.5H7.5A3.5 3.5 0 0 0 4 18.5V20 M9.75 11.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M20 20v-1.3a3.3 3.3 0 0 0-2.5-3.2 M15 4.7a3.5 3.5 0 0 1 0 6.6",
  health:
    "M12 20s-7.5-4.6-7.5-10.2A4.3 4.3 0 0 1 12 7.3a4.3 4.3 0 0 1 7.5 2.5C19.5 15.4 12 20 12 20z",
  assistance:
    "M12 21a9 9 0 1 0 0-18 9 9 0 0 0 0 18z M12 15.5a3.5 3.5 0 1 0 0-7 3.5 3.5 0 0 0 0 7z M5.6 5.6l3.9 3.9 M14.5 14.5l3.9 3.9 M18.4 5.6l-3.9 3.9 M9.5 14.5l-3.9 3.9",
} as const;

export type IconName = keyof typeof PATHS;

interface IconProps {
  name: IconName;
  className?: string;
}

export function Icon({ name, className = "size-5" }: IconProps) {
  return (
    <svg
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={2}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
      className={`shrink-0 ${className}`}
    >
      <path d={PATHS[name]} />
    </svg>
  );
}
