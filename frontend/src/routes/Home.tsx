import { useMemo, useState, type FormEvent, type KeyboardEvent } from "react";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router";
import { useHealth, useServices } from "../api/hooks";
import { GROUPS, type Group, type ServiceListItem } from "../api/types";
import { AlertCard } from "../components/AlertCard";
import { Button } from "../components/Button";
import { Chip } from "../components/Chip";
import { GroupChips } from "../components/GroupChips";
import { HeaderIllustration } from "../components/HeaderIllustration";
import { Icon } from "../components/Icon";
import { useOnline } from "../lib/useOnline";
import { SampleDataTag } from "../components/SampleDataTag";
import { ServiceRow } from "../components/ServiceRow";

/** Intent first: ask box, then topics by life event, then services with what/cost/time. */
export default function Home() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const services = useServices();
  const health = useHealth();
  const online = useOnline();
  const [message, setMessage] = useState("");
  const [group, setGroup] = useState<Group | null>(null);
  const [office, setOffice] = useState<string | null>(null);

  const ask = (text: string) => {
    const trimmed = text.trim();
    if (trimmed && online) void navigate("/chat", { state: { message: trimmed } });
  };
  const onSubmit = (e: FormEvent) => {
    e.preventDefault();
    ask(message);
  };
  const onKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(message);
    }
  };

  const all = useMemo(() => services.data ?? [], [services.data]);
  const offices = useMemo(() => [...new Set(all.map((s) => s.office))], [all]);
  const shown = all.filter((s) => (!group || s.group === group) && (!office || s.office === office));
  const sections = GROUPS.map((g) => ({ group: g, items: shown.filter((s) => s.group === g) })).filter(
    (s) => s.items.length > 0,
  );
  const open = (s: ServiceListItem) => ask(s.name);

  return (
    <div className="flex flex-col gap-8">
      <section className="flex flex-col gap-3">
        <div className="flex items-center justify-between gap-3">
          <label htmlFor="ask" className="text-heading font-bold">
            {t("home.title")}
          </label>
          <HeaderIllustration />
        </div>
        <form onSubmit={onSubmit} className="flex flex-col gap-3">
          <textarea
            id="ask"
            rows={3}
            value={message}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder={t("home.placeholder")}
            aria-describedby="ask-hint"
            maxLength={2000}
            className="w-full resize-none rounded-md border-2 border-border-strong bg-surface p-3 text-lead text-fg placeholder:text-fg-muted"
          />
          <p id="ask-hint" className="text-body text-fg-muted">
            {online ? t("home.hint") : t("offline.askDisabled")}
          </p>
          <Button type="submit" icon="send" block disabled={!online}>
            {t("home.ask")}
          </Button>
        </form>
      </section>

      <section aria-labelledby="topics" className="flex flex-col gap-3">
        <h2 id="topics" className="text-title font-bold">
          {t("home.topics")}
        </h2>
        <GroupChips selected={group} onPick={(g) => setGroup((cur) => (cur === g ? null : g))} />
      </section>

      <section aria-labelledby="services" className="flex flex-col gap-4" aria-busy={services.isPending}>
        <div className="flex items-center justify-between gap-3">
          <h2 id="services" className="text-title font-bold">
            {t("home.services")}
          </h2>
          <SampleDataTag meta={health.data} />
        </div>

        {services.isPending ? <p className="text-body text-fg-muted">{t("home.loading")}…</p> : null}
        {services.isError ? (
          <AlertCard
            action={
              <Button variant="secondary" onClick={() => void services.refetch()}>
                {t("home.retry")}
              </Button>
            }
          >
            {t("home.error")}
          </AlertCard>
        ) : null}
        {services.isSuccess && sections.length === 0 ? (
          <p className="text-body">{t("home.noResults")}</p>
        ) : null}

        {sections.map(({ group: g, items }) => (
          <div key={g} className="flex flex-col gap-3">
            <h3 className="flex items-center gap-2 text-lead font-bold text-primary">
              <Icon name={g} />
              {t(`groups.${g}`)}
            </h3>
            <ul className="flex flex-col gap-3">
              {items.map((s) => (
                <li key={s.id}>
                  <ServiceRow service={s} onOpen={open} disabled={!online} />
                </li>
              ))}
            </ul>
          </div>
        ))}
      </section>

      {offices.length > 0 ? (
        <section aria-labelledby="offices" className="flex flex-col gap-3">
          <h2 id="offices" className="text-lead font-bold">
            {t("home.byOffice")}
          </h2>
          <ul className="flex flex-wrap gap-2">
            {offices.map((o) => (
              <li key={o}>
                <Chip icon="building" selected={office === o} onClick={() => setOffice((cur) => (cur === o ? null : o))}>
                  {o}
                </Chip>
              </li>
            ))}
          </ul>
        </section>
      ) : null}
    </div>
  );
}
