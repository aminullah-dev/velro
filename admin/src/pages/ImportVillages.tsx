import { useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ApiError, api, session } from "../api/client";
import {
  Empty, ErrorBanner, Loading, Ltr, PageHeader, Stat, Table, gate,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface RowProblem {
  row_number: number;
  column: string;
  reason: string;
  value: string | null;
  blocking: boolean;
}

interface DuplicateProposal {
  row_number: number;
  incoming_name: string;
  existing_village_id: string | null;
  existing_name: string;
  score: number;
  same_district: boolean;
  reason: string;
}

interface ParsedVillage {
  row_number: number;
  district_code: string;
  name: string;
  aliases: string[];
  code: string | null;
  latitude: string | null;
  longitude: string | null;
}

interface Preview {
  job_id: string;
  filename: string;
  total_rows: number;
  valid_rows: number;
  problem_count: number;
  blocking_count: number;
  duplicate_count: number;
  will_create_count: number;
  problems: RowProblem[];
  duplicates: DuplicateProposal[];
  will_create: ParsedVillage[];
}

interface CommitResult {
  job_id: string;
  villages_created: number;
  aliases_created: number;
  stations_created: number;
  skipped_duplicates: number;
}

interface ImportJob {
  id: string; entity: string; filename: string; status: string;
  total_rows: number; valid_rows: number; error_rows: number;
  duplicate_rows: number; created_rows: number;
  created_at: string; committed_at: string | null;
}

/**
 * Village import, section 49.
 *
 * Deliberately two screens in one: what the file contains, then what will
 * happen. Nothing is written until the operator has seen both, because section
 * 7 forbids merging similar names without proof — the importer proposes, a
 * person decides, and two villages of the same name in different valleys stay
 * two records.
 */
export function ImportVillagesPage() {
  const { t, num, dateTime } = useStrings();
  const client = useQueryClient();
  const fileInput = useRef<HTMLInputElement>(null);

  const [preview, setPreview] = useState<Preview | null>(null);
  const [accepted, setAccepted] = useState<Set<number>>(new Set());
  const [createStations, setCreateStations] = useState(true);
  const [result, setResult] = useState<CommitResult | null>(null);
  const [uploadError, setUploadError] = useState<unknown>(null);
  const [uploading, setUploading] = useState(false);

  const history = useQuery({
    queryKey: ["imports"],
    queryFn: () => api.get<ImportJob[]>("/admin/imports"),
  });

  /**
   * Uploaded with fetch rather than the shared client: this is the one
   * multipart request in the product, and forcing a JSON content-type on it
   * would strip the boundary the server needs.
   */
  async function upload(file: File) {
    setUploading(true);
    setUploadError(null);
    setResult(null);
    setPreview(null);
    setAccepted(new Set());

    const form = new FormData();
    form.append("file", file);
    form.append("entity", "villages");

    try {
      const response = await fetch("/api/v1/admin/imports/villages/preview", {
        method: "POST",
        headers: { authorization: `Bearer ${session.access ?? ""}` },
        body: form,
      });
      const body = await response.json();
      if (!response.ok) {
        const error = body?.error ?? {};
        throw new ApiError(
          error.code ?? "INTERNAL_ERROR",
          response.status,
          error.context ?? {},
          error.request_id ?? null,
        );
      }
      setPreview(body.data as Preview);
    } catch (caught) {
      setUploadError(caught instanceof ApiError ? caught : ApiError.offline());
    } finally {
      setUploading(false);
      if (fileInput.current) fileInput.current.value = "";
    }
  }

  const commit = useMutation({
    mutationFn: (job: string) =>
      api.post<CommitResult>(`/admin/imports/villages/${job}/commit`, {
        accept_rows: [...accepted],
        create_stations: createStations,
      }),
    onSuccess: (committed) => {
      setResult(committed);
      setPreview(null);
      client.invalidateQueries({ queryKey: ["imports"] });
      // The geography changed, so everything that reads it is now stale.
      client.invalidateQueries({ queryKey: ["districts"] });
      client.invalidateQueries({ queryKey: ["villages"] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
    },
  });

  function toggle(row: number) {
    setAccepted((current) => {
      const next = new Set(current);
      if (next.has(row)) next.delete(row);
      else next.add(row);
      return next;
    });
  }

  function reason(code: string): string {
    // The server sends "repeated_in_file_at_row_2"; the row is already shown
    // in its own column, so only the kind needs translating.
    const base = code.startsWith("repeated_in_file") ? "repeated_in_file" : code;
    const key = `admin.import.reason.${base}`;
    const rendered = t(key);
    return rendered === key ? code : rendered;
  }

  const totalToCreate = (preview?.will_create_count ?? 0) + accepted.size;

  return (
    <>
      <PageHeader title={t("admin.import.title")} subtitle={t("admin.import.subtitle")} />

      {!preview && !result && (
        <div className="card" style={{ marginBottom: "var(--s-5)" }}>
          <input
            ref={fileInput}
            type="file"
            accept=".csv,.json,.xlsx,.xlsm"
            disabled={uploading}
            onChange={(event) => {
              const file = event.target.files?.[0];
              if (file) upload(file);
            }}
          />
          <p className="page-sub">{t("admin.import.accepted_formats")}</p>
          <p className="page-sub">{t("admin.import.optional_columns")}</p>
        </div>
      )}

      {uploading && <Loading />}
      {uploadError && <ErrorBanner error={uploadError} />}
      {commit.error && <ErrorBanner error={commit.error} />}

      {result && (
        <>
          <div className="banner info">
            {t("admin.import.committed", {
              villages: num(result.villages_created),
              aliases: num(result.aliases_created),
              stations: num(result.stations_created),
              skipped: num(result.skipped_duplicates),
            })}
          </div>

          {/* The import creates villages and stations; it does not create the
              routes that make them reachable. Without this the operator
              finishes an import believing the work is done, and every new
              station is invisible to every passenger. Offered here because
              this is the moment it is needed. */}
          {result.stations_created > 0 && (
            <BuildRoutes stationsCreated={result.stations_created} />
          )}

          <button className="primary" onClick={() => setResult(null)}>
            {t("admin.import.start_over")}
          </button>
        </>
      )}

      {preview && (
        <>
          <div className="grid stats" style={{ marginBottom: "var(--s-5)" }}>
            <Stat labelKey="admin.import.total_rows" value={num(preview.total_rows)} />
            <Stat labelKey="admin.import.will_create" value={num(totalToCreate)} />
            <Stat
              labelKey="admin.import.blocking"
              value={num(preview.blocking_count)}
              attention={preview.blocking_count > 0}
            />
            <Stat
              labelKey="admin.import.duplicates"
              value={num(preview.duplicate_count)}
              attention={preview.duplicate_count > 0}
            />
          </div>

          {preview.duplicates.length > 0 && (
            <>
              <h2 className="page-title" style={{ fontSize: 17, marginBottom: "var(--s-2)" }}>
                {t("admin.import.duplicates_title")}
              </h2>
              {/* The whole point of the screen. Nothing here is ticked by
                  default: the safe outcome is to skip, not to create. */}
              <p className="page-sub" style={{ marginBottom: "var(--s-3)" }}>
                {t("admin.import.duplicates_hint")}
              </p>
              <Table
                head={
                  <tr>
                    <th>{t("admin.import.row")}</th>
                    <th>{t("admin.import.incoming")}</th>
                    <th>{t("admin.import.existing")}</th>
                    <th className="num">{t("admin.import.similarity")}</th>
                    <th>{t("admin.col.status")}</th>
                    <th>{t("admin.import.keep_both")}</th>
                  </tr>
                }
              >
                {preview.duplicates.map((duplicate) => (
                  <tr key={duplicate.row_number}>
                    <td className="num">{num(duplicate.row_number)}</td>
                    <td>{duplicate.incoming_name}</td>
                    <td>{duplicate.existing_name}</td>
                    <td className="num">{num(Math.round(duplicate.score * 100))}%</td>
                    <td><span className="chip attention">{reason(duplicate.reason)}</span></td>
                    <td>
                      <label className="row" style={{ gap: "var(--s-2)" }}>
                        <input
                          type="checkbox"
                          style={{ minHeight: "auto" }}
                          checked={accepted.has(duplicate.row_number)}
                          onChange={() => toggle(duplicate.row_number)}
                        />
                      </label>
                    </td>
                  </tr>
                ))}
              </Table>
            </>
          )}

          {preview.problems.length > 0 && (
            <>
              <h2 className="page-title" style={{ fontSize: 17, margin: "var(--s-8) 0 var(--s-3)" }}>
                {t("admin.import.problems_title")}
              </h2>
              <Table
                head={
                  <tr>
                    <th>{t("admin.import.row")}</th>
                    <th>{t("admin.col.name")}</th>
                    <th>{t("admin.col.value")}</th>
                    <th>{t("admin.col.status")}</th>
                  </tr>
                }
              >
                {preview.problems.map((problem, index) => (
                  <tr key={`${problem.row_number}-${problem.column}-${index}`}>
                    <td className="num">{num(problem.row_number)}</td>
                    <td><Ltr>{problem.column}</Ltr></td>
                    <td>{problem.value ?? "—"}</td>
                    <td>
                      {/* A malformed coordinate does not lose the village; a
                          missing name does. Saying which is which stops an
                          operator hunting for rows that were never dropped. */}
                      <span className={`chip ${problem.blocking ? "failed" : "attention"}`}>
                        {reason(problem.reason)}
                        {" · "}
                        {t(problem.blocking
                          ? "admin.import.blocking_flag"
                          : "admin.import.warning_flag")}
                      </span>
                    </td>
                  </tr>
                ))}
              </Table>
            </>
          )}

          <h2 className="page-title" style={{ fontSize: 17, margin: "var(--s-8) 0 var(--s-3)" }}>
            {t("admin.import.will_create_title")}
          </h2>
          {preview.will_create.length === 0 && accepted.size === 0 ? (
            <Empty messageKey="admin.import.nothing_to_import" />
          ) : (
            <Table
              head={
                <tr>
                  <th>{t("admin.import.row")}</th>
                  <th>{t("admin.col.district")}</th>
                  <th>{t("admin.col.name")}</th>
                  <th>{t("admin.col.aliases")}</th>
                </tr>
              }
            >
              {preview.will_create.map((village) => (
                <tr key={village.row_number}>
                  <td className="num">{num(village.row_number)}</td>
                  <td><Ltr>{village.district_code}</Ltr></td>
                  <td>{village.name}</td>
                  <td>{village.aliases.join("، ") || "—"}</td>
                </tr>
              ))}
            </Table>
          )}

          <div className="row" style={{ margin: "var(--s-5) 0" }}>
            <label className="row" style={{ gap: "var(--s-2)" }}>
              <input
                type="checkbox"
                style={{ minHeight: "auto" }}
                checked={createStations}
                onChange={(event) => setCreateStations(event.target.checked)}
              />
              <span>{t("admin.import.create_stations")}</span>
            </label>
            <div className="spacer" />
            <button
              className="primary"
              disabled={commit.isPending || totalToCreate === 0}
              onClick={() => commit.mutate(preview.job_id)}
            >
              {t("admin.import.commit", { count: num(totalToCreate) })}
            </button>
          </div>
        </>
      )}

      <h2 className="page-title" style={{ fontSize: 17, margin: "var(--s-8) 0 var(--s-3)" }}>
        {t("admin.import.history")}
      </h2>
      {/* gate() also covers the paused state, which a plain isLoading
          check falls straight through -- see check-query-gates.mjs. */}
      {gate(history) ?? ((history.data ?? []).length === 0 ? (
        <Empty messageKey="admin.empty.audit" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.created")}</th>
              <th>{t("admin.col.name")}</th>
              <th>{t("admin.col.status")}</th>
              <th className="num">{t("admin.import.total_rows")}</th>
              <th className="num">{t("admin.import.will_create")}</th>
              <th className="num">{t("admin.import.duplicates")}</th>
            </tr>
          }
        >
          {(history.data ?? []).map((job) => (
            <tr key={job.id}>
              <td>{dateTime(job.created_at)}</td>
              <td><Ltr>{job.filename}</Ltr></td>
              <td>
                <span className={`chip ${job.status === "COMMITTED" ? "active" : ""}`}>
                  {job.status}
                </span>
              </td>
              <td className="num">{num(job.total_rows)}</td>
              <td className="num">{num(job.created_rows)}</td>
              <td className="num">{num(job.duplicate_rows)}</td>
            </tr>
          ))}
        </Table>
      ))}
    </>
  );
}


interface GenerateResult {
  templates_processed: number;
  routes_created: number;
  routes_updated: number;
  stations_covered: number;
}

/**
 * Build the routes an import's stations need.
 *
 * A station with no route is not on the network, whatever the map says: it
 * cannot be chosen as an origin and nothing can be booked from it. The
 * endpoint has existed since the route engine was built and nothing called it,
 * so every village imported so far was invisible.
 *
 * Regenerating is safe -- an existing route for a (template, station) pair is
 * updated rather than duplicated -- so this is offered as a plain button
 * rather than hidden behind a confirmation.
 */
function BuildRoutes({ stationsCreated }: { stationsCreated: number }) {
  const { t, num } = useStrings();

  const generate = useMutation({
    mutationFn: () => api.post<GenerateResult>("/admin/routes/generate", {}),
  });

  return (
    <div className="card" style={{ marginBlockEnd: "var(--s-4)" }}>
      <p>{t("admin.routes.generate_needed", { stations: num(stationsCreated) })}</p>
      <p style={{ color: "var(--text-muted)", fontSize: 13 }}>
        {t("admin.routes.generate_hint")}
      </p>

      {generate.error && <ErrorBanner error={generate.error} />}

      {generate.data ? (
        <div className="banner info">
          {t("admin.routes.generated", {
            created: num(generate.data.routes_created),
            updated: num(generate.data.routes_updated),
            stations: num(generate.data.stations_covered),
          })}
        </div>
      ) : (
        <button
          className="primary"
          disabled={generate.isPending}
          onClick={() => generate.mutate()}
        >
          {t("admin.routes.generate")}
        </button>
      )}
    </div>
  );
}
