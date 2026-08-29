import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, session } from "../api/client";
import {
  Empty, ErrorBanner, ErrorState, Loading, Ltr, PageHeader, Table,
} from "../components/ui";
import { useStrings } from "../i18n/strings";

interface Driver {
  id: string; full_name: string | null; phone: string;
  approval_status: string; plate_number: string | null;
}

interface Document {
  id: string;
  document_type_code: string;
  status: string;
  expires_on: string | null;
  rejection_reason: string | null;
  uploaded_at: string;
  reviewed_at: string | null;
  is_current: boolean;
}

interface Checklist {
  required: string[];
  missing: string[];
  documents: Document[];
  approval_status: string;
  can_work: boolean;
}

/**
 * Driver approvals, sections 28 and 51.
 *
 * The reviewer has to actually look at the photograph, so the image is on the
 * screen rather than behind a download. It is fetched with the operator's token
 * and held as a blob: there is no URL that would show an identity card to
 * anyone who happened to have the link.
 */
export function ApprovalsPage() {
  const { t, dateTime } = useStrings();
  const client = useQueryClient();
  const [selected, setSelected] = useState<string | null>(null);
  const [viewing, setViewing] = useState<Document | null>(null);

  const drivers = useQuery({
    queryKey: ["drivers", "pending"],
    queryFn: () => api.get<Driver[]>("/admin/drivers?approval_status=PENDING"),
  });

  const checklist = useQuery({
    queryKey: ["driver-documents", selected],
    queryFn: () => api.get<Checklist>(`/admin/drivers/${selected}/documents`),
    enabled: Boolean(selected),
  });

  const review = useMutation({
    mutationFn: (input: { id: string; verified: boolean; reason?: string; expires?: string }) =>
      api.post(`/admin/documents/${input.id}/review`, {
        verified: input.verified,
        rejection_reason: input.reason ?? null,
        expires_on: input.expires || null,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["driver-documents", selected] });
      client.invalidateQueries({ queryKey: ["drivers"] });
    },
  });

  const approve = useMutation({
    mutationFn: (driverId: string) => api.post(`/admin/drivers/${driverId}/approve`),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["drivers"] });
      client.invalidateQueries({ queryKey: ["driver-documents", selected] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      setSelected(null);
    },
  });

  if (drivers.isLoading) return <Loading />;
  if (drivers.error) {
    return <ErrorState error={drivers.error} onRetry={() => drivers.refetch()} />;
  }

  const pending = drivers.data ?? [];
  const data = checklist.data;

  return (
    <>
      <PageHeader
        title={t("admin.approvals.title")}
        subtitle={t("admin.approvals.subtitle")}
      />

      {review.error && <ErrorBanner error={review.error} />}
      {approve.error && <ErrorBanner error={approve.error} />}

      {pending.length === 0 ? (
        <Empty messageKey="admin.approvals.none" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.name")}</th>
              <th>{t("admin.col.phone")}</th>
              <th>{t("admin.col.status")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {pending.map((driver) => (
            <tr key={driver.id}>
              <td>{driver.full_name ?? "—"}</td>
              <td><Ltr>{driver.phone}</Ltr></td>
              <td><span className="chip attention">{t("admin.approvals.pending")}</span></td>
              <td>
                <button
                  className={`small${selected === driver.id ? " primary" : ""}`}
                  onClick={() => setSelected(driver.id === selected ? null : driver.id)}
                >
                  {t("admin.approvals.documents")}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {selected && (
        <div style={{ marginTop: "var(--s-8)" }}>
          <h2 className="page-title" style={{ fontSize: 17, marginBottom: "var(--s-3)" }}>
            {t("admin.approvals.documents")}
          </h2>

          {checklist.isLoading && <Loading />}
          {data && (
            <>
              {/* Every required type is listed, including the ones never sent --
                  a checklist with silent gaps is not a checklist. */}
              <Table
                head={
                  <tr>
                    <th>{t("admin.col.type")}</th>
                    <th>{t("admin.col.status")}</th>
                    <th>{t("admin.approvals.uploaded")}</th>
                    <th>{t("admin.approvals.expires")}</th>
                    <th>{t("admin.col.actions")}</th>
                  </tr>
                }
              >
                {data.required.map((kind) => {
                  const current = data.documents.find(
                    (d) => d.document_type_code === kind && d.is_current,
                  );
                  return (
                    <tr key={kind}>
                      <td>{t(`document.type.${kind.toLowerCase()}`)}</td>
                      <td>
                        {current ? (
                          <DocumentStatusChip status={current.status} />
                        ) : (
                          <span className="chip failed">
                            {t("admin.approvals.not_uploaded")}
                          </span>
                        )}
                        {current?.rejection_reason && (
                          <div style={{ fontSize: 12, color: "var(--red-700)", marginTop: 4 }}>
                            {current.rejection_reason}
                          </div>
                        )}
                      </td>
                      <td>{current ? dateTime(current.uploaded_at) : "—"}</td>
                      <td>{current?.expires_on ?? "—"}</td>
                      <td>
                        {current && (
                          <div className="row" style={{ gap: "var(--s-2)" }}>
                            <button className="small" onClick={() => setViewing(current)}>
                              {t("admin.approvals.view")}
                            </button>
                            <button
                              className="small primary"
                              disabled={review.isPending}
                              onClick={() => {
                                const expires = prompt(t("admin.approvals.expiry_prompt"), "");
                                if (expires === null) return;
                                review.mutate({
                                  id: current.id, verified: true, expires: expires.trim(),
                                });
                              }}
                            >
                              {t("admin.approvals.verify")}
                            </button>
                            <button
                              className="small danger"
                              disabled={review.isPending}
                              onClick={() => {
                                const reason = prompt(
                                  `${t("admin.approvals.reject_reason")}\n${t("admin.approvals.reject_hint")}`,
                                  "",
                                );
                                if (!reason || !reason.trim()) return;
                                review.mutate({
                                  id: current.id, verified: false, reason: reason.trim(),
                                });
                              }}
                            >
                              {t("admin.approvals.reject")}
                            </button>
                          </div>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </Table>

              <div className="row" style={{ marginTop: "var(--s-5)" }}>
                {data.missing.length > 0 ? (
                  <span className="chip attention">
                    {t("admin.approvals.missing")}:{" "}
                    {data.missing
                      .map((kind) => t(`document.type.${kind.toLowerCase()}`))
                      .join("، ")}
                  </span>
                ) : (
                  <span className="chip active">{t("admin.approvals.complete")}</span>
                )}
                <div className="spacer" />
                <button
                  className="primary"
                  disabled={data.missing.length > 0 || approve.isPending}
                  onClick={() => approve.mutate(selected)}
                >
                  {t("admin.approvals.approve_driver")}
                </button>
              </div>

              {/* Superseded uploads, so a reviewer can see what was sent before. */}
              {data.documents.some((d) => !d.is_current) && (
                <>
                  <h3
                    className="page-sub"
                    style={{ margin: "var(--s-6) 0 var(--s-2)", fontSize: 13 }}
                  >
                    {t("admin.approvals.superseded")}
                  </h3>
                  <Table
                    head={
                      <tr>
                        <th>{t("admin.col.type")}</th>
                        <th>{t("admin.col.status")}</th>
                        <th>{t("admin.approvals.uploaded")}</th>
                      </tr>
                    }
                  >
                    {data.documents
                      .filter((d) => !d.is_current)
                      .map((document) => (
                        <tr key={document.id}>
                          <td>{t(`document.type.${document.document_type_code.toLowerCase()}`)}</td>
                          <td><DocumentStatusChip status={document.status} /></td>
                          <td>{dateTime(document.uploaded_at)}</td>
                        </tr>
                      ))}
                  </Table>
                </>
              )}
            </>
          )}
        </div>
      )}

      {viewing && <DocumentViewer document={viewing} onClose={() => setViewing(null)} />}
    </>
  );
}

function DocumentStatusChip({ status }: { status: string }) {
  const { t } = useStrings();
  const tone =
    status === "VERIFIED" ? "active"
    : status === "PENDING" ? "attention"
    : "failed";
  return <span className={`chip ${tone}`}>{t(`document.status.${status.toLowerCase()}`)}</span>;
}

/**
 * The photograph itself.
 *
 * Fetched with the operator's token and rendered from a blob. An <img src> to
 * the endpoint would not carry the Authorization header, and making the route
 * public so the tag worked would put identity cards behind a guessable URL.
 */
function DocumentViewer({ document: doc, onClose }: { document: Document; onClose: () => void }) {
  const { t } = useStrings();
  const [url, setUrl] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;

    (async () => {
      try {
        const response = await fetch(`/api/v1/admin/documents/${doc.id}/file`, {
          headers: { authorization: `Bearer ${session.access ?? ""}` },
        });
        if (!response.ok) throw new Error(String(response.status));
        const blob = await response.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      } catch {
        if (!cancelled) setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
      // Revoked on close: a blob URL left alive keeps the image in memory and
      // reachable from the console for as long as the tab is open.
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [doc.id]);

  return (
    <div
      onClick={onClose}
      style={{
        position: "fixed", inset: 0, background: "rgba(0,0,0,0.72)",
        display: "grid", placeItems: "center", padding: "var(--s-6)", zIndex: 50,
      }}
    >
      <div className="card" style={{ maxWidth: 720, width: "100%" }} onClick={(e) => e.stopPropagation()}>
        <div className="row" style={{ marginBottom: "var(--s-3)" }}>
          <strong>{t(`document.type.${doc.document_type_code.toLowerCase()}`)}</strong>
          <div className="spacer" />
          <button className="small" onClick={onClose}>{t("common.action.close")}</button>
        </div>
        {failed ? (
          <div className="state">
            <div className="headline">{t("admin.approvals.unreadable")}</div>
            {t("admin.approvals.unreadable_hint")}
          </div>
        ) : url ? (
          <img
            src={url}
            alt={t(`document.type.${doc.document_type_code.toLowerCase()}`)}
            style={{ width: "100%", borderRadius: "var(--r-md)", display: "block" }}
            // A file that downloaded but will not decode is a corrupt upload.
            // Saying so beats an empty box the reviewer cannot interpret -- and
            // it is the reason to reject, not a reason to stare.
            onError={() => setFailed(true)}
          />
        ) : (
          <Loading />
        )}
      </div>
    </div>
  );
}
