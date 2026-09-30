import { useState, type FormEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useOnline } from "../lib/useOnline";
import { Button } from "./Button";

/** Sits above the bottom nav. Enter sends, Shift+Enter is a new line. */
export function ChatInput({ onSend, disabled }: { onSend: (message: string) => void; disabled?: boolean }) {
  const { t } = useTranslation();
  const online = useOnline();
  const off = disabled || !online;
  const [value, setValue] = useState("");
  const submit = () => {
    const trimmed = value.trim();
    if (!trimmed || off) return;
    onSend(trimmed);
    setValue("");
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    submit();
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };
  return (
    <form
      onSubmit={onSubmit}
      className="fixed inset-x-0 bottom-[calc(4rem+env(safe-area-inset-bottom))] z-10 border-t-2 border-border bg-surface"
    >
      {!online ? (
        <p id="chat-offline" className="mx-auto max-w-2xl px-4 pt-2 text-body font-bold">
          {t("offline.askDisabled")}
        </p>
      ) : null}
      <div className="mx-auto flex max-w-2xl items-end gap-2 px-4 py-2">
        <label htmlFor="chat-input" className="sr-only">
          {t("chat.inputLabel")}
        </label>
        <textarea
          id="chat-input"
          rows={1}
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder={t("chat.inputPlaceholder")}
          maxLength={2000}
          disabled={!online}
          aria-describedby={online ? undefined : "chat-offline"}
          className="min-h-11 flex-1 resize-none rounded-md border-2 border-border-strong bg-surface px-3 py-2 text-lead text-fg placeholder:text-fg-muted"
        />
        <Button type="submit" icon="send" disabled={off} aria-label={t("chat.send")} />
      </div>
    </form>
  );
}
