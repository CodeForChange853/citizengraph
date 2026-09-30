import { useId } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "./Button";

/** Tap an option to answer a clarifying question. Each option is sent back as the next message. */
export function ClarifyButtons({
  text,
  options,
  onPick,
}: {
  text?: string;
  options: string[];
  onPick: (option: string) => void;
}) {
  const { t } = useTranslation();
  const titleId = useId();
  return (
    <section aria-labelledby={titleId} className="flex flex-col gap-3">
      <p id={titleId} className="text-lead font-bold">
        {text || t("clarify.title")}
      </p>
      <ul className="flex flex-col gap-2">
        {options.map((option) => (
          <li key={option}>
            <Button variant="secondary" block className="justify-between text-left" onClick={() => onPick(option)}>
              <span>{option}</span>
            </Button>
          </li>
        ))}
      </ul>
    </section>
  );
}
