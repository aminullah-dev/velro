import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import {
  ErrorBanner, ErrorState, Loading, Ltr, PageHeader, Table,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Setting {
  key: string;
  value: unknown;
  value_type: string;
  description_key: string | null;
}

/**
 * Everything an operator may change without a deploy, section 104.
 *
 * The commission rate, the cancellation window, OTP lifetimes, the emergency
 * numbers. Each edit is audited, and the type is checked server-side so a
 * string cannot be written where a number belongs.
 */
export function SettingsPage() {
  const { t } = useStrings();
  const client = useQueryClient();
  const [editing, setEditing] = useState<Record<string, string>>({});

  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ["settings"],
    queryFn: () => api.get<Setting[]>("/admin/settings"),
  });

  const save = useMutation({
    mutationFn: ({ key, value }: { key: string; value: unknown }) =>
      api.patch(`/admin/settings/${key}`, { value }),
    onSuccess: (_result, variables) => {
      setEditing((current) => {
        const next = { ...current };
        delete next[variables.key];
        return next;
      });
      client.invalidateQueries({ queryKey: ["settings"] });
    },
  });

  if (isLoading) return <Loading />;
  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;

  const settings = data ?? [];

  function parse(setting: Setting, raw: string): unknown {
    if (setting.value_type === "int") return Number.parseInt(raw, 10);
    if (setting.value_type === "bool") return raw === "true";
    if (setting.value_type === "list") {
      return raw.split(",").map((part) => part.trim()).filter(Boolean);
    }
    return raw;
  }

  return (
    <>
      <PageHeader title={t("admin.nav.settings")} />
      {save.error && <ErrorBanner error={save.error} />}

      <Table
        head={
          <tr>
            <th>{t("admin.col.setting")}</th>
            <th>{t("admin.col.value")}</th>
            <th>{t("admin.col.actions")}</th>
          </tr>
        }
      >
        {settings.map((setting) => {
          const rendered = Array.isArray(setting.value)
            ? setting.value.join(", ")
            : String(setting.value);
          const draft = editing[setting.key];
          const dirty = draft !== undefined && draft !== rendered;

          return (
            <tr key={setting.key}>
              <td><Ltr>{setting.key}</Ltr></td>
              <td style={{ minWidth: 260 }}>
                <input
                  style={{ width: "100%" }}
                  value={draft ?? rendered}
                  onChange={(event) =>
                    setEditing((current) => ({ ...current, [setting.key]: event.target.value }))
                  }
                />
              </td>
              <td>
                <button
                  className="small primary"
                  disabled={!dirty || save.isPending}
                  onClick={() =>
                    save.mutate({ key: setting.key, value: parse(setting, draft ?? rendered) })
                  }
                >
                  {t("admin.action.save")}
                </button>
              </td>
            </tr>
          );
        })}
      </Table>
    </>
  );
}
