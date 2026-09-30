import { motion } from "motion/react";
import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router";
import { useChat, useServices } from "../api/hooks";
import type { ChatResponse, Group, Lang } from "../api/types";
import { AlertCard } from "../components/AlertCard";
import { AnswerCard } from "../components/AnswerCard";
import { Button } from "../components/Button";
import { ChatInput } from "../components/ChatInput";
import { ClarifyButtons } from "../components/ClarifyButtons";
import { FallbackCard } from "../components/FallbackCard";
import { GroupChips } from "../components/GroupChips";
import { SampleDataTag } from "../components/SampleDataTag";
import { addTurn, newTurnId, resetChat, useChatState } from "../lib/chatStore";

function syntheticClarify(options: string[], lang: Lang): ChatResponse {
  return { session_id: "", language: lang, kind: "clarify", text: "", sections: [], clarify_options: options, meta: {} };
}

function AssistantTurn({
  response,
  interactive,
  onPick,
  onPickGroup,
}: {
  response: ChatResponse;
  interactive: boolean;
  onPick: (option: string) => void;
  onPickGroup: (group: Group) => void;
}) {
  const { kind, text } = response;
  return (
    <div className="flex flex-col gap-4">
      {kind === "clarify" ? (
        interactive ? (
          <ClarifyButtons text={text} options={response.clarify_options} onPick={onPick} />
        ) : text ? (
          <p className="text-lead">{text}</p>
        ) : null
      ) : kind === "answer" ? (
        <>
          <div className="flex flex-wrap items-center justify-between gap-2">
            <p className="text-lead">{text}</p>
            <SampleDataTag meta={response.meta} />
          </div>
          {response.sections.map((section) => (
            <AnswerCard key={section.service_id} section={section} />
          ))}
        </>
      ) : (
        <FallbackCard kind={kind === "refusal" ? "refusal" : "fallback"} text={text} onPickGroup={onPickGroup} />
      )}
    </div>
  );
}

export default function Chat() {
  const { t, i18n } = useTranslation();
  const lang: Lang = i18n.language === "fil" ? "fil" : "en";
  const location = useLocation();
  const navigate = useNavigate();
  const { turns, sessionId } = useChatState();
  const chat = useChat();
  const services = useServices();
  const [failed, setFailed] = useState<string | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);
  const shownTurns = useRef(0);

  const run = useCallback(
    async (message: string, sid: string | null) => {
      setFailed(null);
      try {
        const res = await chat.mutateAsync({ message, lang, session_id: sid });
        addTurn({ id: newTurnId(), role: "assistant", response: res }, res.session_id);
      } catch {
        setFailed(message);
      }
    },
    [chat, lang],
  );

  const send = useCallback(
    (message: string, sid: string | null = sessionId) => {
      addTurn({ id: newTurnId(), role: "user", text: message });
      void run(message, sid);
    },
    [run, sessionId],
  );

  // A question typed on Home (or a service row tapped there) starts a new conversation.
  const started = useRef(false);
  useEffect(() => {
    const message = (location.state as { message?: string } | null)?.message;
    if (!message || started.current) return;
    started.current = true;
    resetChat();
    send(message, null);
    void navigate(".", { replace: true, state: null });
  }, [location.state, navigate, send]);

  const pickGroup = (group: Group) => {
    const label = t(`groups.${group}`);
    const names = (services.data ?? []).filter((s) => s.group === group).map((s) => s.name);
    if (names.length === 0) {
      send(label);
      return;
    }
    addTurn({ id: newTurnId(), role: "user", text: label });
    addTurn({ id: newTurnId(), role: "assistant", response: syntheticClarify(names, lang) });
  };

  useEffect(() => {
    if (turns.length > shownTurns.current && shownTurns.current > 0) {
      const calm = window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
      bottomRef.current?.scrollIntoView?.({ block: "end", behavior: calm ? "auto" : "smooth" });
    }
    shownTurns.current = turns.length;
  }, [turns.length, chat.isPending]);

  const last = turns[turns.length - 1];
  const busy = chat.isPending;

  return (
    <div className="flex flex-col gap-5 pb-24">
      <h1 className="sr-only">{t("nav.ask")}</h1>
      <p role="status" className="sr-only">
        {busy ? t("chat.loading") : last?.role === "assistant" ? t("chat.ready") : ""}
      </p>

      {turns.length === 0 && !busy ? (
        <section className="flex flex-col gap-4 rounded-lg border-2 border-border bg-surface p-4 shadow-card">
          <p className="text-lead font-bold">{t("chat.empty")}</p>
          <GroupChips onPick={pickGroup} />
        </section>
      ) : (
        <div className="flex justify-end">
          <Button
            variant="ghost"
            icon="ask"
            onClick={() => {
              resetChat();
              void navigate("/");
            }}
          >
            {t("chat.newQuestion")}
          </Button>
        </div>
      )}

      {turns.map((turn, i) => (
        <motion.div
          key={turn.id}
          initial={{ opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.2 }}
        >
          {turn.role === "user" ? (
            <div className="flex justify-end">
              <p className="max-w-[85%] rounded-lg rounded-br-sm bg-primary-bg px-4 py-3 text-lead text-on-primary">
                <span className="sr-only">{t("chat.you")}: </span>
                {turn.text}
              </p>
            </div>
          ) : (
            <AssistantTurn
              response={turn.response}
              interactive={i === turns.length - 1 && !busy}
              onPick={send}
              onPickGroup={pickGroup}
            />
          )}
        </motion.div>
      ))}

      {busy ? <p className="text-lead text-fg-muted">{t("chat.loading")}…</p> : null}
      {failed ? (
        <AlertCard
          action={
            <Button variant="secondary" onClick={() => void run(failed, sessionId)}>
              {t("chat.retry")}
            </Button>
          }
        >
          {t("chat.error")}
        </AlertCard>
      ) : null}
      <div ref={bottomRef} />
      <ChatInput onSend={(m) => send(m)} disabled={busy} />
    </div>
  );
}
