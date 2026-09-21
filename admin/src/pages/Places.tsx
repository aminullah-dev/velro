import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { gate } from "../components/gate";
import { InputDialog } from "../components/InputDialog";
import { Empty, ErrorBanner, Ltr, PageHeader, Pager, Table } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface PlaceRow {
  id: string;
  name: string;
  status: "APPROVED" | "PENDING" | "REJECTED";
  district_id: string;
  district_name: string;
  village_id: string | null;
  village_name: string | null;
  nearest_station_name: string | null;
  latitude: number;
  longitude: number;
  report_count: number;
  last_reported_at: string;
  created_at: string;
}

type PlaceStatus = PlaceRow["status"];
const LIMIT = 100;

/**
 * Names passengers gave to where they stood (ADR 0015).
 *
 * The queue behind "automatic, then a person": a name that matched a known
 * village was approved on its own, and everything else waits here, shown to
 * no other passenger until somebody reads it and says it is a place. Most
 * reported first -- many people giving one name is the strongest evidence a
 * place is called that.
 *
 * Nobody's name is on this page, because nobody's name is in the table.
 */
export function PlacesPage() {
  const { t, num, dateTime } = useStrings();
  const client = useQueryClient();
  const [status, setStatus] = useState<PlaceStatus>("PENDING");
  const [offset, setOffset] = useState(0);
  const [renaming, setRenaming] = useState<PlaceRow | null>(null);

  const listQuery = useQuery({
    queryKey: ["places", status, offset],
    queryFn: () =>
      api.list<PlaceRow[]>(`/admin/places?status=${status}&limit=${LIMIT}&offset=${offset}`),
  });

  const decide = useMutation({
    mutationFn: (input: { id: string; approve: boolean; name?: string }) =>
      input.approve
        ? api.post(`/admin/places/${input.id}/approve`, { name: input.name ?? null })
        : api.post(`/admin/places/${input.id}/reject`),
    onSuccess: () => client.invalidateQueries({ queryKey: ["places"] }),
  });

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const rows = listQuery.data?.data ?? [];
  const total = Number(listQuery.data?.meta?.total ?? rows.length);

  return (
    <>
      <PageHeader
        title={t("admin.nav.places")}
        subtitle={t("admin.places.subtitle")}
        actions={
          <button className="small" onClick={() => listQuery.refetch()}>
            {t("admin.action.refresh")}
          </button>
        }
      />

      <div className="row" style={{ marginBottom: "var(--s-3)" }}>
        <select
          value={status}
          aria-label={t("admin.col.status")}
          onChange={(event) => {
            setStatus(event.target.value as PlaceStatus);
            setOffset(0);
          }}
        >
          {/* Literal keys, one per status: the locale check reads them. */}
          <option value="PENDING">{t("admin.places.status.pending")}</option>
          <option value="APPROVED">{t("admin.places.status.approved")}</option>
          <option value="REJECTED">{t("admin.places.status.rejected")}</option>
        </select>
      </div>

      {decide.error && <ErrorBanner error={decide.error} />}

      <InputDialog
        open={renaming !== null}
        titleKey="admin.places.rename"
        confirmKey="admin.places.approve"
        hintKey="admin.places.rename_hint"
        initialValue={renaming?.name ?? ""}
        onCancel={() => setRenaming(null)}
        onConfirm={(name) => {
          if (renaming) decide.mutate({ id: renaming.id, approve: true, name });
          setRenaming(null);
        }}
      />

      {rows.length === 0 ? (
        <Empty messageKey="admin.places.none" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.name")}</th>
              <th>{t("admin.col.district")}</th>
              <th>{t("admin.places.matched")}</th>
              <th>{t("admin.places.station")}</th>
              <th className="num">{t("admin.places.reports")}</th>
              <th>{t("admin.places.last_reported")}</th>
              <th>{t("admin.places.point")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {rows.map((place) => (
            <tr key={place.id}>
              <td style={{ fontWeight: 600 }}>{place.name}</td>
              <td>{place.district_name}</td>
              <td>
                {place.village_name ? (
                  <span className="chip active">{place.village_name}</span>
                ) : (
                  <span style={{ color: "var(--text-muted)" }}>—</span>
                )}
              </td>
              <td>{place.nearest_station_name ?? "—"}</td>
              <td className="num">{num(place.report_count)}</td>
              <td>{dateTime(place.last_reported_at)}</td>
              {/* A coordinate is read digit by digit, so never mirrored. */}
              <td>
                <Ltr>
                  {place.latitude.toFixed(5)}, {place.longitude.toFixed(5)}
                </Ltr>
              </td>
              <td>
                <div className="row" style={{ gap: "var(--s-2)" }}>
                  {place.status !== "APPROVED" && (
                    <button
                      className="small primary"
                      disabled={decide.isPending}
                      onClick={() => decide.mutate({ id: place.id, approve: true })}
                    >
                      {t("admin.places.approve")}
                    </button>
                  )}
                  <button
                    className="small"
                    disabled={decide.isPending}
                    onClick={() => setRenaming(place)}
                  >
                    {t("admin.places.rename")}
                  </button>
                  {place.status !== "REJECTED" && (
                    <button
                      className="small danger"
                      disabled={decide.isPending}
                      onClick={() => decide.mutate({ id: place.id, approve: false })}
                    >
                      {t("admin.places.reject")}
                    </button>
                  )}
                </div>
              </td>
            </tr>
          ))}
        </Table>
      )}

      <Pager total={total} limit={LIMIT} offset={offset} onChange={setOffset} />
    </>
  );
}
