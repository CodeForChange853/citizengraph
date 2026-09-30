import type { Section } from "../api/types";
import { Icon } from "./Icon";
import { ChecklistCard } from "./ChecklistCard";
import { FeesList } from "./FeesList";
import { InfoScent } from "./InfoScent";
import { PendingBanner } from "./PendingBanner";
import { RelatedRoute } from "./RelatedRoute";
import { StepsTimeline } from "./StepsTimeline";
import { WhereToGo } from "./WhereToGo";
import { useMemo } from "react";

/**
 * One card per service. Order: summary, what to bring, fees, steps, where to go, what else you need.
 * A pending_lgu service shows only its name, the calm banner and the office: no numbers, even if sent.
 */
export function AnswerCard({ section }: { section: Section }) {
  const pending = section.info_status === "pending_lgu";
  const meta = useMemo(
    () => ({
      serviceId: section.service_id,
      name: section.service_name,
      office: section.office,
      items: section.checklist,
    }),
    [section],
  );
  const offices = [section.office, ...section.related.map((r) => r.office)];
  const headingId = `answer-${section.service_id}`;

  return (
    <article
      aria-labelledby={headingId}
      className="flex flex-col gap-5 rounded-lg border-2 border-border bg-surface p-4 shadow-card"
    >
      <header className="flex flex-col gap-2">
        <h2 id={headingId} className="text-heading font-bold">
          {section.service_name}
        </h2>
        <InfoScent summary={section.summary} status={section.info_status} size="fact" />
        {pending ? null : (
          <ul className="flex flex-col gap-1">
            {section.notes.map((note) => (
              <li key={note} className="flex gap-2 text-body text-fg-muted">
                <Icon name="info" className="mt-1 size-4" />
                {note}
              </li>
            ))}
          </ul>
        )}
      </header>

      {pending ? (
        <PendingBanner />
      ) : (
        <>
          <ChecklistCard meta={meta} />
          <FeesList serviceId={section.service_id} fees={section.fees} total={section.summary.fee_text} />
          <StepsTimeline serviceId={section.service_id} steps={section.steps} />
        </>
      )}
      <WhereToGo serviceId={section.service_id} offices={pending ? [section.office] : offices} />
      {pending ? null : <RelatedRoute serviceId={section.service_id} related={section.related} />}
    </article>
  );
}
