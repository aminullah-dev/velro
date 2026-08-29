import { useQuery } from "@tanstack/react-query";
import { api } from "../api/client";
import { Empty, ErrorState, Loading, Ltr, PageHeader, Table } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Vehicle {
  id: string; driver_id: string; driver_name: string | null;
  vehicle_type_code: string; plate_number: string; seat_capacity: number;
  brand: string | null; model: string | null; colour: string | null; status: string;
}

export function VehiclesPage() {
  const { t, num } = useStrings();
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["vehicles"],
    queryFn: () => api.get<Vehicle[]>("/admin/vehicles"),
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const vehicles = data ?? [];

  return (
    <>
      <PageHeader title={t("admin.nav.vehicles")} />
      {vehicles.length === 0 ? (
        <Empty messageKey="admin.empty.drivers" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.plate")}</th>
              <th>{t("admin.col.driver")}</th>
              <th>{t("admin.col.type")}</th>
              <th>{t("admin.col.name")}</th>
              <th className="num">{t("admin.col.capacity")}</th>
              <th>{t("admin.col.status")}</th>
            </tr>
          }
        >
          {vehicles.map((vehicle) => (
            <tr key={vehicle.id}>
              {/* A plate is read character by character; never mirrored. */}
              <td><Ltr>{vehicle.plate_number}</Ltr></td>
              <td>{vehicle.driver_name ?? "—"}</td>
              <td>
                <span className="chip">
                  {t(`vehicle_type.${vehicle.vehicle_type_code.toLowerCase()}`)}
                </span>
              </td>
              <td>{[vehicle.brand, vehicle.model].filter(Boolean).join(" ") || "—"}</td>
              <td className="num">{num(vehicle.seat_capacity)}</td>
              <td>
                <span className={`chip ${vehicle.status === "ACTIVE" ? "active" : "ended"}`}>
                  {t(`vehicle.status.${vehicle.status.toLowerCase()}`)}
                </span>
              </td>
            </tr>
          ))}
        </Table>
      )}
    </>
  );
}
