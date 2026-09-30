import { useTranslation } from "react-i18next";
import { NavLink } from "react-router";
import { Icon, type IconName } from "./Icon";

const ITEMS: { to: string; key: "ask" | "saved" | "help"; icon: IconName; end?: boolean }[] = [
  { to: "/", key: "ask", icon: "ask", end: true },
  { to: "/saved", key: "saved", icon: "bookmark" },
  { to: "/help", key: "help", icon: "help" },
];

/** Three items only. The current page is marked with a bar and bold text, not colour alone. */
export function BottomNav() {
  const { t } = useTranslation();
  return (
    <nav
      aria-label={t("nav.label")}
      className="fixed inset-x-0 bottom-0 z-20 border-t-2 border-border bg-surface pb-[env(safe-area-inset-bottom)]"
    >
      <ul className="mx-auto flex max-w-2xl">
        {ITEMS.map(({ to, key, icon, end }) => (
          <li key={key} className="flex-1">
            <NavLink
              to={to}
              end={end}
              className={({ isActive }) =>
                `flex min-h-16 flex-col items-center justify-center gap-0.5 border-t-4 px-2 text-body ${
                  isActive
                    ? "border-primary font-bold text-primary"
                    : "border-transparent text-fg-muted"
                }`
              }
            >
              <Icon name={icon} className="size-6" />
              {t(`nav.${key}`)}
            </NavLink>
          </li>
        ))}
      </ul>
    </nav>
  );
}
