import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Icon, type IconName } from "./Icon";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "accent";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-primary-bg text-on-primary hover:bg-primary-hover border-2 border-primary-bg",
  secondary: "bg-surface text-primary border-2 border-primary hover:bg-primary-soft-bg",
  ghost: "bg-transparent text-primary border-2 border-transparent hover:bg-primary-soft-bg",
  accent: "bg-accent-bg text-on-accent border-2 border-on-accent",
};

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: ButtonVariant;
  icon?: IconName;
  block?: boolean;
  children?: ReactNode;
}

/** 44px minimum height and width. Text label always present. */
export function Button({
  variant = "primary",
  icon,
  block = false,
  className = "",
  type = "button",
  children,
  ...rest
}: ButtonProps) {
  return (
    <button
      type={type}
      className={`inline-flex min-h-11 min-w-11 cursor-pointer items-center justify-center gap-2 rounded-md px-4 py-2 text-body font-bold disabled:cursor-not-allowed disabled:opacity-60 ${VARIANTS[variant]} ${block ? "w-full" : ""} ${className}`}
      {...rest}
    >
      {icon ? <Icon name={icon} /> : null}
      {children}
    </button>
  );
}
