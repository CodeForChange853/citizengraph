import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

interface ChipProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  icon?: IconName;
  selected?: boolean;
  children: ReactNode;
}

/** A toggle-style topic chip. Selected state has a check mark, not only a colour. */
export function Chip({ icon, selected, className = "", type = "button", children, ...rest }: ChipProps) {
  const state =
    selected === undefined
      ? {}
      : { "aria-pressed": selected };
  return (
    <button
      type={type}
      className={`inline-flex min-h-11 cursor-pointer items-center gap-2 rounded-full border-2 px-4 py-1.5 text-body font-bold ${
        selected
          ? "border-primary bg-primary-soft-bg text-on-primary-soft"
          : "border-border-strong bg-surface text-fg hover:bg-surface-2"
      } ${className}`}
      {...state}
      {...rest}
    >
      {selected ? <Icon name="check" /> : icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
}
