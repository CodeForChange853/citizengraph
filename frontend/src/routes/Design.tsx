import { useState, type ReactNode } from "react";
import { useTranslation } from "react-i18next";
import fixtures from "../api/fixtures.json";
import type { Group, Section } from "../api/types";
import { AnswerCard } from "../components/AnswerCard";
import { Button } from "../components/Button";
import { ChecklistCard } from "../components/ChecklistCard";
import { Chip } from "../components/Chip";
import { ClarifyButtons } from "../components/ClarifyButtons";
import { DisplayControls } from "../components/DisplayControls";
import { FallbackCard } from "../components/FallbackCard";
import { GroupChips } from "../components/GroupChips";
import { Icon } from "../components/Icon";
import { InfoScent } from "../components/InfoScent";
import { LanguageToggle } from "../components/LanguageToggle";
import { OfflineBanner } from "../components/OfflineBanner";
import { PendingBanner } from "../components/PendingBanner";
import { SampleDataTag } from "../components/SampleDataTag";
import { checkPairs, checkPalette, checkUseRules } from "../design/contrast.js";
import type { Tokens } from "../design/contrast.js";
import tokensJson from "../design/tokens.json";

const tokens = tokensJson as Tokens;
const results = checkPairs(tokens);
const problems = [...checkPalette(tokens), ...checkUseRules(tokens)];
const sample = (fixtures.sections.en as unknown as Record<string, Section>).business_permit!;
const pendingSample = (fixtures.sections.en as unknown as Record<string, Section>)
  .death_registration_timely!;

function Block({ title, children }: { title: string; children: ReactNode }) {
  return (
    <section className="flex flex-col gap-4 border-t-2 border-border pt-6">
      <h2 className="text-heading font-bold">{title}</h2>
      {children}
    </section>
  );
}

function Pass({ ok }: { ok: boolean }) {
  return (
    <span className="inline-flex items-center gap-1 font-bold">
      <Icon name={ok ? "check" : "alert"} className="size-4" />
      {ok ? "Pass" : "Fail"}
    </span>
  );
}

const TYPE_SCALE = [
  ["text-fact font-bold", "Key fact 1.5rem: ₱235.50"],
  ["text-heading font-bold", "Heading 1.75rem"],
  ["text-title font-bold", "Title 1.375rem"],
  ["text-lead", "Lead 1.125rem: what to bring"],
  ["text-body", "Body 1rem (16px minimum): Bring your ID and the form."],
  ["text-caption", "Caption 0.875rem: tags and labels only"],
] as const;

export default function Design() {
  const { t } = useTranslation();
  const [picked, setPicked] = useState<string | null>(null);
  const [group, setGroup] = useState<Group | null>("business");
  const [pressed, setPressed] = useState(true);
  const failing = results.filter((r) => !r.pass).length;

  return (
    <div className="mx-auto flex max-w-3xl flex-col gap-8 px-4 pb-16 pt-6">
      <header className="flex flex-col gap-4">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h1 className="text-heading font-bold">Design system</h1>
          <LanguageToggle />
        </div>
        <p className="text-body text-fg-muted">
          Every token and component on one page. Switch language, colours and text size to check
          each one. Colour values come from <code>src/design/tokens.json</code>.
        </p>
        <DisplayControls />
        <p className="text-body font-bold">
          {failing === 0 && problems.length === 0
            ? `All ${results.length} colour pairs pass WCAG AA in light and dark.`
            : `${failing} contrast failures, ${problems.length} palette problems.`}
        </p>
      </header>

      <Block title="Palette">
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {Object.entries(tokens.palette).map(([name, { hex, family }]) => (
            <li key={name} className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="size-11 shrink-0 rounded-sm border-2 border-border-strong"
                style={{ background: hex }}
              />
              <span className="text-body leading-tight">
                <span className="block font-bold">{name}</span>
                <span className="block text-fg-muted">
                  {hex} · {family}
                </span>
              </span>
            </li>
          ))}
        </ul>
        <p className="text-body text-fg-muted">
          Red is for alerts and errors only. Yellow sits on blue or navy, or is a background with navy
          text. Success and info use blue with an icon.
        </p>
      </Block>

      <Block title="Roles in the current theme">
        <ul className="grid grid-cols-2 gap-3 sm:grid-cols-3">
          {Object.keys(tokens.themes.light!).map((role) => (
            <li key={role} className="flex items-center gap-3">
              <span
                aria-hidden="true"
                className="size-11 shrink-0 rounded-sm border-2 border-border-strong"
                style={{ background: `var(--${role})` }}
              />
              <span className="text-body font-bold leading-tight">{role}</span>
            </li>
          ))}
        </ul>
      </Block>

      <Block title="Contrast pairs (WCAG AA)">
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left text-body">
            <caption className="sr-only">Contrast ratio of every text and background pair</caption>
            <thead>
              <tr className="border-b-2 border-border-strong">
                <th scope="col" className="py-2 pr-3">Pair</th>
                <th scope="col" className="py-2 pr-3">Sample</th>
                <th scope="col" className="py-2 pr-3">Light</th>
                <th scope="col" className="py-2">Dark</th>
              </tr>
            </thead>
            <tbody>
              {tokens.pairs.map((pair) => {
                const light = results.find((r) => r.theme === "light" && r.label === pair.label)!;
                const dark = results.find((r) => r.theme === "dark" && r.label === pair.label)!;
                return (
                  <tr key={pair.label} className="border-b border-border align-top">
                    <td className="py-2 pr-3">
                      {pair.label}
                      <span className="block text-caption text-fg-muted">
                        {pair.fg} on {pair.bg} · needs {light.min}:1
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      <span
                        className="inline-block rounded-sm border border-border px-2 py-1 font-bold"
                        style={{ color: `var(--${pair.fg})`, background: `var(--${pair.bg})` }}
                      >
                        Aa
                      </span>
                    </td>
                    <td className="py-2 pr-3">
                      {light.ratio.toFixed(2)}:1 <Pass ok={light.pass} />
                    </td>
                    <td className="py-2">
                      {dark.ratio.toFixed(2)}:1 <Pass ok={dark.pass} />
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </Block>

      <Block title="Type scale">
        <div className="flex flex-col gap-2">
          {TYPE_SCALE.map(([cls, label]) => (
            <p key={label} className={cls}>
              {label}
            </p>
          ))}
        </div>
      </Block>

      <Block title="Buttons">
        <div className="flex flex-wrap gap-3">
          <Button>Primary</Button>
          <Button variant="secondary">Secondary</Button>
          <Button variant="ghost">Ghost</Button>
          <Button variant="accent">Accent</Button>
          <Button icon="send">With icon</Button>
          <Button disabled>Disabled</Button>
        </div>
      </Block>

      <Block title="Chips">
        <div className="flex flex-wrap gap-2">
          <Chip icon="business">Plain chip</Chip>
          <Chip selected={pressed} onClick={() => setPressed((p) => !p)}>
            Selected chip (tap)
          </Chip>
        </div>
        <p className="text-body font-bold">Topic chips as filters</p>
        <GroupChips selected={group} onPick={(g) => setGroup((cur) => (cur === g ? null : g))} />
      </Block>

      <Block title="Information scent">
        <div className="flex flex-col gap-3">
          <InfoScent summary={sample.summary} status="confirmed" size="fact" />
          <InfoScent summary={sample.summary} status="confirmed" />
          <InfoScent
            summary={{ requirement_count: 5, fee_text: null, time_text: "1 week, 1 hour, 40 minutes" }}
            status="confirmed"
          />
          <InfoScent summary={pendingSample.summary} status="pending_lgu" />
        </div>
      </Block>

      <Block title="Checklist card (tick items; saved on this device)">
        <div className="rounded-lg border-2 border-border bg-surface p-4 shadow-card">
          <ChecklistCard
            meta={{
              serviceId: "design-sample",
              name: sample.service_name,
              office: sample.office,
              items: sample.checklist.slice(0, 5),
            }}
          />
        </div>
      </Block>

      <Block title="Pending banner (info_status = pending_lgu)">
        <PendingBanner />
      </Block>

      <Block title="Clarify buttons">
        <div className="rounded-lg border-2 border-border bg-surface p-4 shadow-card">
          <ClarifyButtons
            options={["Business Permit", "Sanitary Permit"]}
            onPick={setPicked}
          />
        </div>
        <p className="text-body text-fg-muted" aria-live="polite">
          {picked ? `You tapped: ${picked}` : "Tap an option."}
        </p>
      </Block>

      <Block title="Fallback and refusal cards">
        <FallbackCard onPickGroup={(g) => setGroup(g)} />
        <FallbackCard kind="refusal" onPickGroup={(g) => setGroup(g)} />
      </Block>

      <Block title="Offline banner and tags">
        <div className="overflow-hidden rounded-md">
          <OfflineBanner forceShow />
        </div>
        <div className="flex items-center gap-3">
          <SampleDataTag meta={{ mock: true }} />
          <span className="text-body">{t("app.prototype")}</span>
        </div>
      </Block>

      <Block title="Answer card (confirmed)">
        <AnswerCard section={sample} />
      </Block>

      <Block title="Answer card (pending_lgu)">
        <AnswerCard section={pendingSample} />
      </Block>

      <Block title="Language toggle">
        <LanguageToggle />
        <p className="text-body">
          {t("lang.label")}: {t("lang.en")} / {t("lang.fil")}
        </p>
      </Block>
    </div>
  );
}
