import type { ReactNode } from "react";
import { Icon } from "./Icon";

/** The only place red is used: a real error. Light red card, navy text, red icon (AA in both themes). */
export function AlertCard({ children, action }: { children: ReactNode; action?: ReactNode }) {
  return (
    <div role="alert" className="flex flex-col gap-3 rounded-md border-l-8 border-alert bg-alert-bg p-4 text-on-alert">
      <div className="flex gap-3">
        <span className="mt-0.5 text-alert">
          <Icon name="alert" className="size-6" />
        </span>
        <p className="text-body font-bold">{children}</p>
      </div>
      {action ? <div>{action}</div> : null}
    </div>
  );
}
