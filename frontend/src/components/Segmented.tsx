interface Option<T extends string> {
  value: T;
  label: string;
  /** Screen-reader name when the visible label is short (for example "EN"). */
  title?: string;
}

interface SegmentedProps<T extends string> {
  label: string;
  value: T;
  options: Option<T>[];
  onChange: (value: T) => void;
}

/** A small group of toggle buttons. Each is at least 44px high. */
export function Segmented<T extends string>({ label, value, options, onChange }: SegmentedProps<T>) {
  return (
    <div
      role="group"
      aria-label={label}
      className="inline-flex overflow-hidden rounded-md border-2 border-border-strong"
    >
      {options.map((o) => {
        const active = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={active}
            aria-label={o.title}
            onClick={() => onChange(o.value)}
            className={`min-h-11 min-w-11 cursor-pointer px-3 text-body font-bold ${
              active ? "bg-primary-bg text-on-primary" : "bg-surface text-fg hover:bg-surface-2"
            }`}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
