import { useTranslation } from "react-i18next";
import { GROUPS, type Group } from "../api/types";
import { Chip } from "./Chip";

/** The four life-event topics. Used on Home, in the fallback card and to filter services. */
export function GroupChips({
  onPick,
  selected,
}: {
  onPick: (group: Group) => void;
  /** When given, chips act as filters (pressed state); otherwise they are plain buttons. */
  selected?: Group | null;
}) {
  const { t } = useTranslation();
  return (
    <ul className="flex flex-wrap gap-2">
      {GROUPS.map((group) => (
        <li key={group}>
          <Chip
            icon={group}
            selected={selected === undefined ? undefined : selected === group}
            onClick={() => onPick(group)}
          >
            {t(`groups.${group}`)}
          </Chip>
        </li>
      ))}
    </ul>
  );
}
