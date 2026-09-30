import type { ServiceListItem } from "../api/types";
import { Icon } from "./Icon";
import { InfoScent } from "./InfoScent";

/** One tappable row: name, information scent (what to bring, fee, time), office. */
export function ServiceRow({
  service,
  onOpen,
  disabled = false,
}: {
  service: ServiceListItem;
  onOpen: (service: ServiceListItem) => void;
  disabled?: boolean;
}) {
  return (
    <button
      type="button"
      onClick={() => onOpen(service)}
      disabled={disabled}
      className="flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-lg border-2 border-border bg-surface p-4 text-left shadow-card hover:bg-surface-2 disabled:cursor-not-allowed"
    >
      <span className="flex min-w-0 flex-1 flex-col gap-1">
        <span className="text-lead font-bold">{service.name}</span>
        <InfoScent summary={service.summary} status={service.info_status} />
        <span className="flex items-center gap-1.5 text-body text-fg-muted">
          <Icon name="building" className="size-4" />
          {service.office}
        </span>
      </span>
      <Icon name="chevronRight" className="size-6 text-primary" />
    </button>
  );
}
