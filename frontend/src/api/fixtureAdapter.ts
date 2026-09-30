import fixtures from "./fixtures.json";
import type { ApiClient } from "./client";
import type { ChatRequest, ChatResponse, Lang, Section, ServiceListItem } from "./types";

// Mirrors mock_chat() in src/citizengraph/api/main.py. A parity test runs both on the same cases.

type Kind = ChatResponse["kind"];

const sections = fixtures.sections as unknown as Record<Lang, Record<string, Section>>;
const text = fixtures.text as Record<Lang, Record<string, string>>;
const names = fixtures.names as Record<string, string>;

export function mockChat(message: string, lang: Lang) {
  const t = text[lang];
  const msg = message.toLowerCase();
  const none = { serviceIds: [] as string[], clarifyIds: [] as string[] };
  if (new RegExp(fixtures.refusal_pattern).test(msg)) {
    return { kind: "refusal" as Kind, text: t.refusal ?? "", ...none };
  }
  const ids = fixtures.routes
    .filter((r) => r.keywords.some((k) => msg.includes(k)))
    .map((r) => r.service_id);
  if (ids.length) {
    const list = ids.map((i) => names[i]).join(", ");
    return {
      kind: "answer" as Kind,
      text: (t.answer ?? "").replace("{names}", list),
      serviceIds: ids,
      clarifyIds: [] as string[],
    };
  }
  for (const amb of fixtures.ambiguous) {
    if (msg.includes(amb.keyword)) {
      return {
        kind: "clarify" as Kind,
        text: t.clarify ?? "",
        serviceIds: [] as string[],
        clarifyIds: amb.options,
      };
    }
  }
  if (fixtures.greetings.includes(msg.trim())) {
    return {
      kind: "clarify" as Kind,
      text: t.clarify ?? "",
      serviceIds: [] as string[],
      clarifyIds: fixtures.default_options,
    };
  }
  return { kind: "fallback" as Kind, text: t.fallback ?? "", ...none };
}

export function createFixtureAdapter(): ApiClient {
  return {
    mode: "fixtures",
    async services() {
      return fixtures.services as ServiceListItem[];
    },
    async chat(req: ChatRequest): Promise<ChatResponse> {
      const r = mockChat(req.message, req.lang);
      return {
        session_id: req.session_id ?? crypto.randomUUID(),
        language: req.lang,
        kind: r.kind,
        text: r.text,
        sections: r.serviceIds.flatMap((id) => {
          const s = sections[req.lang][id];
          return s ? [s] : [];
        }),
        clarify_options: r.clarifyIds.map((id) => names[id] ?? id),
        meta: { mock: true, source: "fixtures" },
      };
    },
  };
}
