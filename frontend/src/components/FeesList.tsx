import { useTranslation } from "react-i18next";
import type { FeeItem } from "../api/types";

/** "What it costs". A missing fee is never shown as free: the office is asked instead. */
export function FeesList({ serviceId, fees, total }: { serviceId: string; fees: FeeItem[]; total: string | null }) {
  const { t } = useTranslation();
  const id = `fees-${serviceId}`;
  return (
    <section aria-labelledby={id} className="flex flex-col gap-3">
      <h3 id={id} className="text-title font-bold">
        {t("answer.fees")}
      </h3>
      {fees.length === 0 ? (
        <p className="text-body">{t("answer.feesNone")}</p>
      ) : (
        <dl className="flex flex-col">
          {fees.map((fee) => (
            <div key={fee.label} className="flex items-baseline justify-between gap-4 border-b border-border py-2">
              <dt className="text-body">{fee.label}</dt>
              <dd className="text-lead font-bold">{fee.amount_text}</dd>
            </div>
          ))}
          {fees.length > 1 && total ? (
            <div className="flex items-baseline justify-between gap-4 pt-3">
              <dt className="text-lead font-bold">{t("answer.total")}</dt>
              <dd className="text-fact font-bold">{total}</dd>
            </div>
          ) : null}
        </dl>
      )}
    </section>
  );
}
