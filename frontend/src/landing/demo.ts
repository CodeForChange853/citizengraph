// The demo script: what is typed, the illustrative query, and when each sound cue falls on the timeline.
// Timings follow docs/landing_motion_spec.md, section 4.
import fixtures from "../api/fixtures.json";
import type { ServiceListItem } from "../api/types";
import { beat, type Cue } from "./timeline";

/** Typed in beat 1. The same text is shown in both UI languages: citizens write mixed messages. */
// NEEDS-NATIVE-REVIEW: Taglish demo question, not yet checked by a native speaker.
export const DEMO_QUESTION = "Ano po ang requirements para sa business permit?";

/**
 * Shown in beat 4, labelled "illustrative". It is a picture of the idea, not the model's real output:
 * read-only, every node labelled, every relationship typed, and a LIMIT. It passes the project's
 * guardrail (`citizengraph.guardrail.validator.validate_cypher`); keep it that way when editing.
 */
export const DEMO_CYPHER = [
  "MATCH (s:Service {id: 'business_permit'})",
  "      -[:REQUIRES]->(r:Requirement)",
  "RETURN r.text",
  "LIMIT 25",
].join("\n");

/** The guardrail rules the demo ticks off (i18n keys under landing.guard). */
export const GUARD_CHECKS = ["readOnly", "labels", "schema", "limit"] as const;

/** The sample card names this service and its office as the mock API's sample data has them. */
export const DEMO_SERVICE = (fixtures.services as ServiceListItem[]).find((s) => s.id === "business_permit")!;

/** Service counts per office, from the four received charters (see CLAUDE.md, data status). */
export const OFFICES = [
  { id: "BPLO", services: 7 },
  { id: "LCRO", services: 17 },
  { id: "CHO", services: 15 },
  { id: "CSWDO", services: 1 },
] as const;
export const SERVICE_TOTAL = OFFICES.reduce((n, o) => n + o.services, 0);

// Beat 1: the line crosses the stage, then the question is typed in bursts: one character every
// TYPE_EVERY ms inside a word and a short pause after each word (the rhythm measured in the reference).
export const LINE_MS = 520;
const TYPE_START = 600;
const TYPE_EVERY = 44;
const WORD_PAUSE = 90;

/** When each character of the question appears, in ms into beat 1. */
export const CHAR_AT: number[] = (() => {
  let at = TYPE_START;
  return Array.from(DEMO_QUESTION, (ch) => {
    const mine = at;
    at += TYPE_EVERY + (ch === " " ? WORD_PAUSE : 0);
    return mine;
  });
})();

/** The question is sent (Enter) this long into beat 1. */
export const ENTER_AT = CHAR_AT[CHAR_AT.length - 1]! + 180;

/** How many characters of the question are typed `ms` into beat 1. */
export function typedChars(ms: number): number {
  let count = 0;
  while (count < CHAR_AT.length && CHAR_AT[count]! <= ms) count++;
  return count;
}

// Beat 3: each office callout lights in turn.
const CALLOUT_START = 0.2;
const CALLOUT_SPAN = 0.3;

/** When office `i`'s callout lights, as a share of beat 3. */
export function calloutAt(i: number): number {
  return CALLOUT_START + (CALLOUT_SPAN * i) / OFFICES.length;
}

// Beat 4: the query is written out, then the guardrail checks tick one by one on the reference's beat.
const CYPHER_MS = 2000;
const TICK_START = 2400;
const TICK_EVERY = 455;

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
    ch === " " ? null : { at: beat("ask").start + CHAR_AT[i]!, kind: "key" },
  ).filter((c): c is Cue => c !== null),
  { at: beat("ask").start + ENTER_AT, kind: "enter" },
  ...OFFICES.map((_, i): Cue => ({ at: beat("offices").start + calloutAt(i) * beat("offices").dur, kind: "blip" })),
  ...GUARD_CHECKS.map((_, i): Cue => ({ at: beat("query").start + TICK_START + i * TICK_EVERY, kind: "tick" })),
];
