/**
 * Which versions of the two apps are still being opened.
 *
 * The question behind it is "can we stop caring about 1.1 yet", and the only
 * honest source is the apps themselves. They send an app, a platform and a
 * version when they check for an update and nothing else, so these are
 * launches, not people: one driver opening the app twenty times a day is
 * twenty. The share is a share of launches, and the note above says so,
 * because a number that looks like a head count will be read as one.
 */
import type { AppKind, AppVersion, AppVersionCount, AppsReport } from "../api/operations";
import { useStrings } from "../i18n/strings";
import { Ltr, Table } from "./ui";

const APPS: AppKind[] = ["passenger", "driver"];

export function AppVersions({ apps }: { apps: AppsReport }) {
  const { t } = useStrings();
  return (
    <>
      <p className="muted section-note">{t("admin.apps.note", { days: apps.window_days })}</p>
      <div className="grid apps">
        {APPS.map((app) => (
          <AppBlock
            key={app}
            app={app}
            latest={apps.latest?.[app] ?? null}
            rows={(apps.versions ?? []).filter((row) => row.app === app)}
          />
        ))}
      </div>
    </>
  );
}

function AppBlock({ app, latest, rows }: {
  app: AppKind;
  latest: AppVersion | null;
  rows: AppVersionCount[];
}) {
  const { t, num } = useStrings();
  const total = rows.reduce((sum, row) => sum + row.checks, 0);
  const sorted = [...rows].sort(
    (a, b) => b.version_code - a.version_code || a.platform.localeCompare(b.platform),
  );

  return (
    <div className="app-block">
      <h3 className="card-title">{t(`admin.apps.${app}`)}</h3>
      <div className="muted app-latest">
        {latest ? (
          <>
            {t("admin.apps.latest")}{" "}
            <Ltr>{latest.version_name} ({latest.version_code})</Ltr>
          </>
        ) : (
          t("admin.apps.latest_none")
        )}
      </div>

      {sorted.length === 0 ? (
        <p className="muted">{t("admin.apps.none")}</p>
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.apps.version")}</th>
              <th className="num">{t("admin.apps.launches")}</th>
              <th>{t("admin.apps.share")}</th>
              <th>{t("admin.col.status")}</th>
            </tr>
          }
        >
          {sorted.map((row) => {
            const share = total > 0 ? Math.round((row.checks / total) * 100) : 0;
            // The published version is the Android release the update check
            // offers; an iOS build number is a different count altogether, so
            // an iOS row is shown but never judged against it.
            const current = latest && row.platform === "android"
              ? row.version_code >= latest.version_code
              : null;
            return (
              <tr key={`${row.platform}-${row.version_code}`} className={current ? "is-latest" : undefined}>
                {/* The platform rides in the version's cell: nearly every row
                    is Android, and a column that says so on every line cost
                    the table its status column at laptop widths. */}
                <td>
                  <Ltr>{row.version_name} ({row.version_code})</Ltr>{" "}
                  <span className="muted">{t(`admin.apps.platform_${row.platform}`)}</span>
                </td>
                <td className="num">{num(row.checks)}</td>
                <td>
                  <span className="share">
                    <span className="share-meter" aria-hidden="true">
                      <span style={{ width: `${share}%` }} />
                    </span>
                    {t("admin.apps.share_value", { value: share })}
                  </span>
                </td>
                <td>
                  {current === null ? "—" : current ? (
                    <span className="chip active">{t("admin.apps.state_latest")}</span>
                  ) : (
                    <span className="chip attention">{t("admin.apps.state_outdated")}</span>
                  )}
                </td>
              </tr>
            );
          })}
        </Table>
      )}
    </div>
  );
}
