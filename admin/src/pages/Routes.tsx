import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, query } from "../api/client";
import { Empty, ErrorBanner, Ltr, PageHeader, Pager, Table, gate } from "../components/ui";
import { InputDialog } from "../components/InputDialog";
import { useStrings } from "../i18n/strings";

interface Route {
  id: string; code: string; route_type: string;
  origin_station_name: string; destination_name: string;
  distance_m: number | null; duration_minutes: number | null;
  status: string; fare_minor: number | null; fare_currency: string | null;
}

const LIMIT = 25;

export function RoutesPage() {
  const { t, num, money } = useStrings();
  const client = useQueryClient();
  const [search, setSearch] = useState("");
  const [offset, setOffset] = useState(0);
  // The route being repriced, with the price it has now.
  const [pricing, setPricing] = useState<{ id: string; current: string } | null>(null);

  const listQuery = useQuery({
    queryKey: ["routes", search, offset],
    queryFn: () =>
      api.list<Route[]>(`/admin/routes${query({ q: search, limit: LIMIT, offset })}`),
  });
  const { data } = listQuery;

  const generate = useMutation({
    mutationFn: () =>
      api.post<{
        routes_created: number;
        routes_updated: number;
        stations_covered: number;
      }>("/admin/routes/generate", {}),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["routes"] });
    },
  });

  const setPrice = useMutation({
    mutationFn: ({ id, amountMinor }: { id: string; amountMinor: number }) =>
      api.post(`/admin/routes/${id}/fare`, { amount_minor: amountMinor, ride_kind: "SHARED" }),
    onSuccess: () => client.invalidateQueries({ queryKey: ["routes"] }),
  });

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const routes = data?.data ?? [];
  const total = Number(data?.meta?.total ?? routes.length);

  return (
    <>
      <PageHeader
        title={t("admin.nav.routes")}
        actions={
          <>
            <input
              value={search}
              placeholder={t("admin.hint.search_routes")}
              onChange={(event) => {
                setSearch(event.target.value);
                setOffset(0);
              }}
            />
            {/* Routes are generated from templates, not hand-made. A station
                added any way other than through the importer -- or a template
                that changed -- leaves routes to build, and this is the only
                place to do it. Regenerating updates rather than duplicates. */}
            <button
              className="small"
              disabled={generate.isPending}
              onClick={() => generate.mutate()}
            >
              {t("admin.routes.generate")}
            </button>
          </>
        }
      />

      {setPrice.error && <ErrorBanner error={setPrice.error} />}
      {generate.error && <ErrorBanner error={generate.error} />}
      {generate.data && (
        <div className="banner info">
          {t("admin.routes.generated", {
            created: num(generate.data.routes_created),
            updated: num(generate.data.routes_updated),
            stations: num(generate.data.stations_covered),
          })}
        </div>
      )}

      <InputDialog
        open={pricing !== null}
        titleKey="admin.prompt.new_price"
        labelKey="admin.col.price"
        confirmKey="admin.action.set_price"
        field="number"
        initialValue={pricing?.current ?? ""}
        destructive={false}
        onCancel={() => setPricing(null)}
        onConfirm={(entered) => {
          if (pricing) {
            // Sent as integer minor units; nothing here does decimal
            // arithmetic on a price.
            setPrice.mutate({
              id: pricing.id,
              amountMinor: Math.round(Number(entered) * 100),
            });
          }
          setPricing(null);
        }}
      />

      {routes.length === 0 ? (
        <Empty messageKey="empty.search_results" />
      ) : (
        <>
          <Table
            head={
              <tr>
                <th>{t("admin.col.route")}</th>
                <th>{t("admin.col.origin")}</th>
                <th>{t("admin.col.destination")}</th>
                <th>{t("admin.col.type")}</th>
                <th className="num">{t("admin.col.distance")}</th>
                <th className="num">{t("admin.col.price")}</th>
                <th>{t("admin.col.actions")}</th>
              </tr>
            }
          >
            {routes.map((route) => (
              <tr key={route.id}>
                <td><Ltr>{route.code}</Ltr></td>
                <td>{route.origin_station_name}</td>
                <td>{route.destination_name}</td>
                <td>
                  <span className="chip">
                    {t(`route.type.${route.route_type.toLowerCase()}`)}
                  </span>
                </td>
                <td className="num">
                  {route.distance_m === null ? "—" : `${num(Math.round(route.distance_m / 1000))} km`}
                </td>
                <td className="num">
                  {route.fare_minor === null
                    ? "—"
                    : money(route.fare_minor, route.fare_currency ?? "AFN")}
                </td>
                <td>
                  <button
                    className="small"
                    disabled={setPrice.isPending || route.fare_minor === null}
                    onClick={() =>
                      setPricing({
                        id: route.id,
                        current: String((route.fare_minor ?? 0) / 100),
                      })
                    }
                  >
                    {t("admin.action.set_price")}
                  </button>
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
