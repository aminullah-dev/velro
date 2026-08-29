import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { api, query } from "../api/client";
import {
  Empty, ErrorState, Loading, Ltr, PageHeader, Pager, Table,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface District {
  id: string; code: string; name: string; alternative_name: string | null;
  status: string; village_count: number; station_count: number;
}
interface Village {
  id: string; code: string; name: string; district_id: string; district_name: string;
  status: string; latitude: number | null; longitude: number | null; station_count: number;
}
interface Destination {
  id: string; code: string; name: string; kind: string;
  parent_id: string | null; parent_name: string | null; sort_order: number; status: string;
}

const LIMIT = 50;

/**
 * The geography, section 48.
 *
 * Districts first because there are four of them and they frame everything
 * else; villages are searchable because there will eventually be hundreds.
 */
export function LocationsPage() {
  const { t, num } = useStrings();
  const [districtId, setDistrictId] = useState("");
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);

  const districts = useQuery({
    queryKey: ["districts"],
    queryFn: () => api.get<District[]>("/admin/districts"),
  });

  const villages = useQuery({
    queryKey: ["villages", districtId, search, offset],
    queryFn: () =>
      api.list<Village[]>(
        `/admin/villages${query({ district_id: districtId, q: search, limit: LIMIT, offset })}`,
      ),
  });

  const destinations = useQuery({
    queryKey: ["destinations"],
    queryFn: () => api.get<Destination[]>("/admin/destinations"),
  });

  if (districts.isLoading) return <Loading />;
  if (districts.error) {
    return <ErrorState error={districts.error} onRetry={() => districts.refetch()} />;
  }

  const villageRows = villages.data?.data ?? [];
  const villageTotal = Number(villages.data?.meta?.total ?? villageRows.length);

  return (
    <>
      <PageHeader title={t("admin.nav.locations")} />

      <h2 className="page-title" style={{ fontSize: 17, marginBottom: "var(--s-3)" }}>
        {t("admin.section.locations")}
      </h2>
      <Table
        head={
          <tr>
            <th>{t("admin.col.code")}</th>
            <th>{t("admin.col.name")}</th>
            <th className="num">{t("admin.col.villages")}</th>
            <th className="num">{t("admin.col.stations")}</th>
            <th>{t("admin.col.status")}</th>
          </tr>
        }
      >
        {(districts.data ?? []).map((district) => (
          <tr key={district.id}>
            <td><Ltr>{district.code}</Ltr></td>
            <td>
              {district.name}
              {district.alternative_name && (
                <span style={{ color: "var(--text-muted)", fontSize: 12 }}>
                  {" · "}{district.alternative_name}
                </span>
              )}
            </td>
            <td className="num">{num(district.village_count)}</td>
            <td className="num">{num(district.station_count)}</td>
            <td>
              <span className="chip active">
                {t(`geo.status.${district.status.toLowerCase()}`)}
              </span>
            </td>
          </tr>
        ))}
      </Table>

      <h2 className="page-title" style={{ fontSize: 17, margin: "var(--s-8) 0 var(--s-3)" }}>
        {t("admin.section.villages")}
      </h2>
      <div className="row" style={{ marginBottom: "var(--s-3)" }}>
        <select
          value={districtId}
          onChange={(event) => {
            setDistrictId(event.target.value);
            setOffset(0);
          }}
        >
          <option value="">{t("admin.filter.all")}</option>
          {(districts.data ?? []).map((district) => (
            <option key={district.id} value={district.id}>{district.name}</option>
          ))}
        </select>
        <input
          value={search}
          placeholder={t("admin.hint.search_villages")}
          onChange={(event) => {
            setSearch(event.target.value);
            setOffset(0);
          }}
        />
      </div>

      {villages.isLoading ? (
        <Loading />
      ) : villageRows.length === 0 ? (
        <Empty messageKey="empty.search_results" />
      ) : (
        <>
          <Table
            head={
              <tr>
                <th>{t("admin.col.code")}</th>
                <th>{t("admin.col.name")}</th>
                <th>{t("admin.col.district")}</th>
                <th className="num">{t("admin.col.stations")}</th>
                <th>{t("admin.col.status")}</th>
              </tr>
            }
          >
            {villageRows.map((village) => (
              <tr key={village.id}>
                <td><Ltr>{village.code}</Ltr></td>
                <td>{village.name}</td>
                <td>{village.district_name}</td>
                <td className="num">{num(village.station_count)}</td>
                <td>
                  <span className={`chip ${village.status === "ACTIVE" ? "active" : "ended"}`}>
                    {t(`geo.status.${village.status.toLowerCase()}`)}
                  </span>
                </td>
              </tr>
            ))}
          </Table>
          <Pager total={villageTotal} limit={LIMIT} offset={offset} onChange={setOffset} />
        </>
      )}

      <h2 className="page-title" style={{ fontSize: 17, margin: "var(--s-8) 0 var(--s-3)" }}>
        {t("admin.section.destinations")}
      </h2>
      <Table
        head={
          <tr>
            <th>{t("admin.col.code")}</th>
            <th>{t("admin.col.name")}</th>
            <th>{t("admin.col.type")}</th>
            <th>{t("admin.col.parent")}</th>
          </tr>
        }
      >
        {(destinations.data ?? []).map((destination) => (
          <tr key={destination.id}>
            <td><Ltr>{destination.code}</Ltr></td>
            <td>{destination.name}</td>
            <td>
              <span className="chip">
                {t(`destination.kind.${destination.kind.toLowerCase()}`)}
              </span>
            </td>
            <td>{destination.parent_name ?? "—"}</td>
          </tr>
        ))}
      </Table>
    </>
  );
}
