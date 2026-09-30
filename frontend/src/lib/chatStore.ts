import { useSyncExternalStore } from "react";
import type { ChatResponse } from "../api/types";
import { readJson, writeJson } from "./storage";

/**
 * The current conversation. Kept in memory so it survives moving between Ask, Saved and Help,
 * and copied to this device so the last answers can be read again with no signal. Nothing is sent
 * anywhere by this store.
 */
export type Turn =
  | { id: string; role: "user"; text: string }
  | { id: string; role: "assistant"; response: ChatResponse };

export interface ChatState {
  turns: Turn[];
  sessionId: string | null;
}

export const CHAT_KEY = "cg.chat.v1";
const MAX_TURNS = 20;
const EMPTY: ChatState = { turns: [], sessionId: null };

function load(): ChatState {
  const saved = readJson<Partial<ChatState>>(CHAT_KEY, {});
  return Array.isArray(saved.turns)
    ? { turns: saved.turns.slice(-MAX_TURNS), sessionId: saved.sessionId ?? null }
    : EMPTY;
}

let state: ChatState = load();
const listeners = new Set<() => void>();

function commit(next: ChatState): void {
  state = { ...next, turns: next.turns.slice(-MAX_TURNS) };
  writeJson(CHAT_KEY, state);
  listeners.forEach((l) => l());
}

let counter = 0;
export const newTurnId = () => `t${Date.now().toString(36)}${(counter++).toString(36)}`;

export function addTurn(turn: Turn, sessionId?: string | null): void {
  commit({
    turns: [...state.turns, turn],
    sessionId: sessionId === undefined ? state.sessionId : sessionId,
  });
}

/** Start a new conversation. */
export function resetChat(): void {
  commit(EMPTY);
}

/** Re-read storage (tests). */
export function reloadChat(): void {
  state = load();
  listeners.forEach((l) => l());
}

export function useChatState(): ChatState {
  return useSyncExternalStore(
    (cb) => {
      listeners.add(cb);
      return () => listeners.delete(cb);
    },
    () => state,
  );
}
