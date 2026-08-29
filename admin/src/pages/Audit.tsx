import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, query } from "../api/client";
import {
  Empty, ErrorState, Loading, Ltr, PageHeader, Pager, Table,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface AuditEntry {
  id: string; occurred_at: string;
  actor_id: string | null; actor_name: string | null; actor_role: string;
  action: string; entity_type: string; entity_id: string;
  before: Record<string, unknown> | null;
  after: Record<string, unknown> | null;
  origin: string;
}

const LIMIT = 50;

/**
 * The audit trail, section 59.
 *
 * Append-only and never rotated. Only the changed fields are stored, which is
 * what keeps a row readable a year later.
 */
export function AuditPage() {
  const { t, dateTime } = useStrings();
  const [offset, setOffset] = useState(0);

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["audit", offset],
    queryFn: () => api.list<AuditEntry[]>(`/admin/audit${query({ limit: LIMIT, offset })}`),
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const entries = data?.data ?? [];
  const total = Number(data?.meta?.total ?? entries.length);

  function summarise(entry: AuditEntry): string {
    if (!entry.before && !entry.after) return "—";
    const keys = new Set([
      ...Object.keys(entry.before ?? {}),
      ...Object.keys(entry.after ?? {}),
    ]);
    const parts = [...keys]
      .map((key) => {
        const from = entry.before?.[key];
        const to = entry.after?.[key];
        if (from !== undefined && to !== undefined) return `${key}: ${from} → ${to}`;
        const only = to ?? from;
        // A field with no value on either side says nothing; rendering it as
        // "device_id: undefined" is worse than omitting it.
        if (only === undefined || only === null) return null;
        return `${key}: ${only}`;
      })
      .filter((part): part is string => part !== null);
    return parts.length > 0 ? parts.join("  ·  ") : "—";
  }

  return (
    <>
      <PageHeader title={t("admin.nav.audit")} />
      {entries.length === 0 ? (
        <Empty messageKey="admin.empty.audit" />
      ) : (
        <>
          <Table
            head={
              <tr>
                <th>{t("admin.col.when")}</th>
                <th>{t("admin.col.who")}</th>
                <th>{t("admin.col.action")}</th>
                <th>{t("admin.col.entity")}</th>
                <th>{t("admin.col.change")}</th>
              </tr>
            }
          >
            {entries.map((entry) => (
              <tr key={entry.id}>
                <td>{dateTime(entry.occurred_at)}</td>
                <td>
                  {entry.actor_name ?? "—"}
                  <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                    {" · "}{entry.actor_role}
                  </span>
                </td>
                <td><Ltr>{entry.action}</Ltr></td>
                <td><Ltr>{entry.entity_type}</Ltr></td>
                <td style={{ whiteSpace: "normal", maxWidth: 420 }}>
                  <Ltr>{summarise(entry)}</Ltr>
                </td>
              </tr>
            ))}
          </Table>
          <Pager total={total} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}
    </>
  );
}
