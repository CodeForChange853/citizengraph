import type { TFunction } from "i18next";
import { useTranslation } from "react-i18next";
import type { InfoStatus, Summary } from "../api/types";
import { Icon } from "./Icon";

/**
 * The "information scent" line: what to bring, what it costs, how long. Pure so tests can call it.
 * A pending_lgu service never shows numbers, whatever the API sent.
 */
export function scentParts(summary: Summary, status: InfoStatus, t: TFunction): string[] {
  if (status === "pending_lgu") return [t("scent.beingChecked")];
  const parts: string[] = [];
  const { requirement_count: count, fee_text: fee, time_text: time } = summary;
  if (count === 0) parts.push(t("scent.noDocuments"));
  else if (count !== null) parts.push(t("scent.requirements", { count }));
  parts.push(fee ?? t("scent.feeNotListed"));
  parts.push(time ? t("scent.timeAbout", { time }) : t("scent.timeNotListed"));
  return parts;
}

interface InfoScentProps {
  summary: Summary;
  status: InfoStatus;
  /** "fact" is larger, for the top of an answer card. */
  size?: "row" | "fact";
}

export function InfoScent({ summary, status, size = "row" }: InfoScentProps) {
  const { t } = useTranslation();
  const parts = scentParts(summary, status, t);
  const pending = status === "pending_lgu";
  return (
    <p
      className={`flex flex-wrap items-center gap-x-2 gap-y-1 ${
        size === "fact" ? "text-fact font-bold" : "text-body text-fg-muted"
      }`}
    >
      {pending ? <Icon name="info" /> : null}
      <span>{parts.join(" · ")}</span>
    </p>
  );
}
