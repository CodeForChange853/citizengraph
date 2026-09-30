import { useCallback, useMemo, useSyncExternalStore } from "react";
import { readJson, writeJson } from "./storage";

/** A checklist kept on this device. There is no account and nothing is sent anywhere. */
export interface SavedChecklist {
  serviceId: string;
  name: string;
  office: string;
  items: string[];
  ticked: string[];
  updatedAt: number;
}

export type ChecklistMeta = Pick<SavedChecklist, "serviceId" | "name" | "office" | "items">;

export const CHECKLIST_KEY = "cg.checklists.v1";

let state: Record<string, SavedChecklist> = readJson(CHECKLIST_KEY, {});
const listeners = new Set<() => void>();

function commit(next: Record<string, SavedChecklist>): void {
  state = next;
  writeJson(CHECKLIST_KEY, state);
  listeners.forEach((l) => l());
}

/** Re-read storage (tests, and other tabs). */
export function reloadChecklists(): void {
  state = readJson(CHECKLIST_KEY, {});
  listeners.forEach((l) => l());
}

export function toggleItem(meta: ChecklistMeta, item: string): void {
  const current = state[meta.serviceId];
  const ticked = new Set(current?.ticked ?? []);
  if (ticked.has(item)) ticked.delete(item);
  else ticked.add(item);
  commit({
    ...state,
    [meta.serviceId]: { ...meta, ticked: [...ticked], updatedAt: Date.now() },
  });
}

/** Keep a list without ticking anything. */
export function keepChecklist(meta: ChecklistMeta): void {
  if (state[meta.serviceId]) return;
  commit({ ...state, [meta.serviceId]: { ...meta, ticked: [], updatedAt: Date.now() } });
}

export function removeChecklist(serviceId: string): void {
  const rest = { ...state };
  delete rest[serviceId];
  commit(rest);
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  const onStorage = (e: StorageEvent) => {
    if (e.key === CHECKLIST_KEY) reloadChecklists();
  };
  window.addEventListener("storage", onStorage);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("storage", onStorage);
  };
}

const getSnapshot = () => state;

export function useSavedChecklists(): SavedChecklist[] {
  const all = useSyncExternalStore(subscribe, getSnapshot);
  return useMemo(() => Object.values(all).sort((a, b) => b.updatedAt - a.updatedAt), [all]);
}

/** Progress counts only items that are still on the current list. */
export function useChecklist(meta: ChecklistMeta) {
  const all = useSyncExternalStore(subscribe, getSnapshot);
  const entry = all[meta.serviceId];
  const ticked = useMemo(
    () => new Set((entry?.ticked ?? []).filter((t) => meta.items.includes(t))),
    [entry, meta.items],
  );
  const toggle = useCallback((item: string) => toggleItem(meta, item), [meta]);
  const keep = useCallback(() => keepChecklist(meta), [meta]);
  const remove = useCallback(() => removeChecklist(meta.serviceId), [meta.serviceId]);
  return { ticked, done: ticked.size, total: meta.items.length, kept: Boolean(entry), toggle, keep, remove };
}
