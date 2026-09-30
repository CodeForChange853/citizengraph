import { useTranslation } from "react-i18next";
import type { Group } from "../api/types";
import { GroupChips } from "./GroupChips";
import { Icon } from "./Icon";

/** Never a dead end: a short honest message plus the four life-event topics. */
export function FallbackCard({
  kind = "fallback",
  text,
  onPickGroup,
}: {
  kind?: "fallback" | "refusal";
  text?: string;
  onPickGroup: (group: Group) => void;
}) {
  const { t } = useTranslation();
  const refusal = kind === "refusal";
  return (
    <section className="flex flex-col gap-4 rounded-lg border-2 border-border bg-surface p-4 shadow-card">
      <div className="flex gap-3">
        <span className="mt-0.5 text-primary">
          <Icon name="info" className="size-6" />
        </span>
        <div>
          <h3 className="text-title font-bold">
            {refusal ? t("fallback.refusalTitle") : t("fallback.title")}
          </h3>
          <p className="text-body">
            {text || (refusal ? t("fallback.refusalBody") : t("fallback.body"))}
          </p>
        </div>
      </div>
      <GroupChips onPick={onPickGroup} />
    </section>
  );
}
