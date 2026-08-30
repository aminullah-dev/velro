import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api, session } from "../api/client";
import { Empty, ErrorBanner, Loading, PageHeader, Phone, Table, gate } from "../components/ui";
import { InputDialog } from "../components/InputDialog";
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
  // Which document is being verified or refused. Ids rather than the row, so a
  // background refresh cannot swap what the open dialog is about.
  const [verifying, setVerifying] = useState<string | null>(null);
  const [rejecting, setRejecting] = useState<string | null>(null);
  const [naming, setNaming] = useState<string | null>(null);

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
    mutationFn: ({ driverId, name }: { driverId: string; name: string }) =>
      api.post(`/admin/drivers/${driverId}/approve`, {
        // Empty means the operator did not answer, which leaves whatever the
        // driver gave alone. Only a name typed here replaces one.
        full_name: name.trim() || null,
      }),
    onSuccess: () => {
      client.invalidateQueries({ queryKey: ["drivers"] });
      client.invalidateQueries({ queryKey: ["driver-documents", selected] });
      client.invalidateQueries({ queryKey: ["dashboard"] });
      setSelected(null);
    },
  });

  const blocked = gate(drivers);
  if (blocked) return blocked;

  const pending = drivers.data ?? [];
  const data = checklist.data;

  return (
    <>
      <PageHeader
        title={t("admin.approvals.title")}
        subtitle={t("admin.approvals.subtitle")}
      />

      {review.error && <ErrorBanner error={review.error} />}

      <InputDialog
        open={verifying !== null}
        titleKey="admin.approvals.expiry_prompt"
        labelKey="admin.col.expires"
        confirmKey="admin.approvals.verify"
        hintKey="admin.approvals.expiry_hint"
        field="date"
        required={false}
        destructive={false}
        onCancel={() => setVerifying(null)}
        onConfirm={(expires) => {
          if (verifying) review.mutate({ id: verifying, verified: true, expires });
          setVerifying(null);
        }}
      />

      {/* The best name in the system: an operator, authenticated, reading a
          tazkira, on the one screen with a decision attached. It is also the
          only place a wrong name can be corrected -- the apply form appears on
          whatever handset a household shares. */}
      <InputDialog
        open={naming !== null}
        titleKey="admin.approvals.record_name"
        labelKey="profile.field.name"
        confirmKey="admin.approvals.approve_driver"
        hintKey="admin.approvals.name_hint"
        field="text"
        required={false}
        destructive={false}
        initialValue={pending.find((d) => d.id === naming)?.full_name ?? ""}
        onCancel={() => setNaming(null)}
        onConfirm={(name) => {
          if (naming) approve.mutate({ driverId: naming, name });
          setNaming(null);
        }}
      />

      <InputDialog
        open={rejecting !== null}
        titleKey="admin.approvals.reject_reason"
        confirmKey="admin.approvals.reject"
        hintKey="admin.approvals.reject_hint"
        onCancel={() => setRejecting(null)}
        onConfirm={(reason) => {
          if (rejecting) review.mutate({ id: rejecting, verified: false, reason });
          setRejecting(null);
        }}
      />
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
              <td>{driver.full_name ?? t("common.value.no_name")}</td>
              <td><Phone number={driver.phone} /></td>
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
              {/* The face and the tazkira first, and together. Everything below
                  is paperwork; this is the question of whether the person is
                  who they say. */}
              <IdentityCheck
                selfie={data.documents.find(
                  (d) => d.document_type_code === "SELFIE" && d.is_current,
                )}
                tazkira={data.documents.find(
                  (d) => d.document_type_code === "NATIONAL_ID" && d.is_current,
                )}
              />

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
                                setVerifying(current.id);
                              }}
                            >
                              {t("admin.approvals.verify")}
                            </button>
                            <button
                              className="small danger"
                              disabled={review.isPending}
                              onClick={() => {
                                setRejecting(current.id);
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
                  onClick={() => setNaming(selected)}
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
 * Fetches one document as a blob URL.
 *
 * Authenticated, so the image cannot be a plain <img src> to the endpoint: the
 * tag would not carry the Authorization header, and making the route public so
 * that it worked would put identity cards behind a guessable URL. The blob is
 * revoked on unmount -- one left alive keeps someone's tazkira in memory and
 * reachable from the console for as long as the tab is open.
 *
 * The id the picture was fetched for is part of the state rather than being
 * cleared by an effect. Clearing happens after paint, so on a switch from one
 * driver to the next the previous driver's face renders for a frame under the
 * new driver's name -- on an identity-check screen, the one wrong thing to
 * show. Comparing the ids instead means a stale result can never be displayed.
 */
function useDocumentImage(id: string | undefined) {
  const [state, setState] = useState<{
    forId?: string;
    url: string | null;
    failed: boolean;
  }>({ url: null, failed: false });

  useEffect(() => {
    if (!id) return;
    let objectUrl: string | null = null;
    let cancelled = false;

    (async () => {
      try {
        const response = await fetch(`/api/v1/admin/documents/${id}/file`, {
          headers: { authorization: `Bearer ${session.access ?? ""}` },
        });
        if (!response.ok) throw new Error(String(response.status));
        const blob = await response.blob();
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setState({ forId: id, url: objectUrl, failed: false });
      } catch {
        if (!cancelled) setState({ forId: id, url: null, failed: true });
      }
    })();

    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [id]);

  return state.forId === id ? state : { url: null, failed: false };
}

/**
 * The face beside the tazkira.
 *
 * The whole point of asking for a photo is comparing it with the document, and
 * a reviewer who has to open one, remember it, close it and open the other is
 * being asked to do that from memory. Side by side is the feature.
 */
function IdentityCheck({
  selfie,
  tazkira,
}: {
  selfie: Document | undefined;
  tazkira: Document | undefined;
}) {
  const { t } = useStrings();
  const face = useDocumentImage(selfie?.id);
  const card = useDocumentImage(tazkira?.id);

  return (
    <div className="card" style={{ marginBottom: "var(--s-4)" }}>
      <div className="row" style={{ marginBottom: "var(--s-3)" }}>
        <strong>{t("admin.approvals.identity")}</strong>
        <div className="spacer" />
        <span style={{ color: "var(--text-muted)", fontSize: 13 }}>
          {t("admin.approvals.compare")}
        </span>
      </div>
      <div className="identity-pair">
        <figure>
          <figcaption>{t("document.type.selfie")}</figcaption>
          {selfie == null ? (
            <p className="hint">{t("admin.approvals.no_selfie")}</p>
          ) : face.failed ? (
            <p className="hint error">{t("admin.approvals.file_unavailable")}</p>
          ) : face.url ? (
            <img src={face.url} alt="" />
          ) : (
            <p className="hint">…</p>
          )}
        </figure>
        <figure>
          <figcaption>{t("document.type.national_id")}</figcaption>
          {tazkira == null ? (
            <p className="hint">{t("admin.approvals.no_tazkira")}</p>
          ) : card.failed ? (
            <p className="hint error">{t("admin.approvals.file_unavailable")}</p>
          ) : card.url ? (
            <img src={card.url} alt="" />
          ) : (
            <p className="hint">…</p>
          )}
        </figure>
      </div>
    </div>
  );
}

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
