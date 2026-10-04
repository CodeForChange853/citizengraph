// The demo script: what is typed, the illustrative query, and when each sound cue falls on the timeline.
import fixtures from "../api/fixtures.json";
import type { ServiceListItem } from "../api/types";
import { beat, type Cue } from "./timeline";

/** Typed in beat 1. The same text is shown in both UI languages: citizens write mixed messages. */
// NEEDS-NATIVE-REVIEW: Taglish demo question, not yet checked by a native speaker.
export const DEMO_QUESTION = "Ano po ang requirements para sa business permit?";

/**
 * Shown in beat 4, labelled "illustrative". It is a picture of the idea, not the model's real output:
 * read-only, every node labelled, every relationship typed, and a LIMIT.
 */
export const DEMO_CYPHER = [
  "MATCH (s:Service {id: 'business_permit'})",
  "      -[:REQUIRES]->(r:Requirement)",
  "RETURN r.text",
  "LIMIT 25",
].join("\n");

/** The guardrail rules the demo ticks off (i18n keys under landing.guard). */
export const GUARD_CHECKS = ["readOnly", "labels", "schema", "limit"] as const;

/** The sample card shows this service exactly as the mock API's sample data has it. */
export const DEMO_SERVICE = (fixtures.services as ServiceListItem[]).find((s) => s.id === "business_permit")!;

/** Service counts per office, from the four received charters (see CLAUDE.md, data status). */
export const OFFICES = [
  { id: "BPLO", services: 7 },
  { id: "LCRO", services: 17 },
  { id: "CHO", services: 15 },
  { id: "CSWDO", services: 1 },
] as const;
export const SERVICE_TOTAL = OFFICES.reduce((n, o) => n + o.services, 0);

// Beat 1: the amber line grows, then the question is typed one character at a time.
const TYPE_START = 500;
const TYPE_EVERY = 48;
const ENTER_AT = TYPE_START + DEMO_QUESTION.length * TYPE_EVERY + 180;

/** How many characters of the question are typed `ms` into beat 1. */
export function typedChars(ms: number): number {
  if (ms < TYPE_START) return 0;
  return Math.min(DEMO_QUESTION.length, Math.floor((ms - TYPE_START) / TYPE_EVERY) + 1);
}

// Beat 4: the query is written out, then the guardrail checks tick one by one.
const CYPHER_MS = 1500;
const TICK_START = 1900;
const TICK_EVERY = 400;

export function cypherChars(ms: number): number {
  if (ms <= 0) return 0;
  return Math.min(DEMO_CYPHER.length, Math.ceil((ms / CYPHER_MS) * DEMO_CYPHER.length));
}

export function guardTicks(ms: number): number {
  if (ms < TICK_START) return 0;
  return Math.min(GUARD_CHECKS.length, Math.floor((ms - TICK_START) / TICK_EVERY) + 1);
}

export const CUES: Cue[] = [
  ...Array.from(DEMO_QUESTION, (ch, i): Cue | null =>
    ch === " " ? null : { at: beat("ask").start + TYPE_START + i * TYPE_EVERY, kind: "key" },
  ).filter((c): c is Cue => c !== null),
  { at: beat("ask").start + ENTER_AT, kind: "enter" },
  ...GUARD_CHECKS.map((_, i): Cue => ({ at: beat("query").start + TICK_START + i * TICK_EVERY, kind: "tick" })),
];
