import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "../api/client";
import { Empty, ErrorBanner, Ltr, PageHeader, Table, gate } from "../components/ui";
import { useStrings } from "../i18n/strings";

interface TicketMessage {
  id: string;
  author_role: string;
  /** Optional so an older API cannot make the panel misattribute a message. */
  is_from_reporter?: boolean;
  body: string;
  is_internal: boolean;
  sent_at: string;
}

interface Ticket {
  id: string;
  reference: string;
  category_code: string;
  subject: string;
  status: string;
  is_urgent: boolean;
  trip_id: string | null;
  booking_id: string | null;
  created_at: string;
  resolved_at: string | null;
  messages: TicketMessage[];
}

interface Queue {
  tickets: Ticket[];
  open: number;
  urgent_open: number;
}

const FILTERS = [
  { key: null, labelKey: "admin.support.filter_all" },
  { key: "OPEN", labelKey: "admin.support.filter_open" },
  { key: "IN_PROGRESS", labelKey: "admin.support.filter_in_progress" },
] as const;

/**
 * The support queue.
 *
 * The ordering is the whole point and it comes from the server, not from here:
 * urgent first, then oldest. Nobody is watching overnight, so a safety report
 * raised at 02:00 must not be pushed down the page by a fare dispute raised at
 * 09:00 — there is no human awake to notice it happening. This page must never
 * re-sort the list it is given.
 */
export function SupportPage() {
  const { t, num, dateTime } = useStrings();
  const [status, setStatus] = useState<string | null>(null);
  const [open, setOpen] = useState<string | null>(null);

  const listQuery = useQuery({
    queryKey: ["support", status],
    queryFn: () =>
      api.get<Queue>(
        `/admin/support/tickets${status ? `?status=${status}` : ""}`,
      ),
    // Short, because this is the queue somebody watches when they are on shift.
    refetchInterval: 30_000,
  });
  const { data } = listQuery;

  const blocked = gate(listQuery);
  if (blocked) return blocked;

  const queue = data ?? { tickets: [], open: 0, urgent_open: 0 };

  return (
    <>
      <PageHeader
        title={t("admin.support.title")}
        subtitle={t("admin.support.subtitle")}
        actions={
          <div className="row" style={{ gap: "var(--s-2)" }}>
            <span className="chip attention">
              {t("admin.support.open_count", { count: num(queue.open) })}
            </span>
            {queue.urgent_open > 0 && (
              <span className="chip failed">
                {t("admin.support.urgent_count", {
                  count: num(queue.urgent_open),
                })}
              </span>
            )}
            <button className="small" onClick={() => listQuery.refetch()}>
              {t("admin.action.refresh")}
            </button>
          </div>
        }
      />

      <div className="row" style={{ gap: "var(--s-2)", marginBlockEnd: "var(--s-4)" }}>
        {FILTERS.map((filter) => (
          <button
            key={filter.labelKey}
            className={`small ${status === filter.key ? "primary" : ""}`}
            onClick={() => setStatus(filter.key)}
          >
            {t(filter.labelKey)}
          </button>
        ))}
      </div>

      {queue.tickets.length === 0 ? (
        <Empty messageKey="admin.support.none" />
      ) : (
        <Table
          head={
            <tr>
              <th>{t("admin.col.reference")}</th>
              <th>{t("admin.col.category")}</th>
              <th>{t("admin.col.status")}</th>
              <th>{t("admin.col.created")}</th>
              <th>{t("admin.col.actions")}</th>
            </tr>
          }
        >
          {queue.tickets.map((ticket) => (
            <tr key={ticket.id}>
              <td>
                {/* A reference is read down a phone line, so never mirrored
                    and never in Eastern digits. */}
                <Ltr>{ticket.reference}</Ltr>
              </td>
              <td>
                <div className="row" style={{ gap: "var(--s-2)" }}>
                  {/* Urgency carries a word, not only a colour: an operator
                      reading in a hurry, or one who cannot distinguish red,
                      must still see which of these is the dangerous one. */}
                  {ticket.is_urgent && (
                    <span className="chip failed">{t("admin.support.urgent")}</span>
                  )}
                  <span>
                    {t(`ticket.category.${ticket.category_code.toLowerCase()}`)}
                  </span>
                </div>
              </td>
              <td>
                <span
                  className={`chip ${
                    ticket.status === "OPEN" ? "attention"
                    : ticket.status === "IN_PROGRESS" ? "attention"
                    : "active"
                  }`}
                >
                  {t(`ticket.status.${ticket.status.toLowerCase()}`)}
                </span>
              </td>
              <td>{dateTime(ticket.created_at)}</td>
              <td>
                <button
                  className="small"
                  onClick={() => setOpen(open === ticket.id ? null : ticket.id)}
                >
                  {t("admin.approvals.view")}
                </button>
              </td>
            </tr>
          ))}
        </Table>
      )}

      {open && (
        <TicketThread
          // Keyed by ticket, so opening a second one cannot inherit the first
          // one's half-typed draft or its internal-note flag.
          key={open}
          ticket={queue.tickets.find((candidate) => candidate.id === open)}
          onClose={() => setOpen(null)}
        />
      )}
    </>
  );
}

/**
 * One request, and everything an operator can do about it.
 *
 * Internal notes are rendered differently from replies, deliberately and
 * loudly: an operator who writes "this driver has three of these" into the
 * wrong box has sent it to the driver.
 */
function TicketThread({
  ticket,
  onClose,
}: {
  ticket: Ticket | undefined;
  onClose: () => void;
}) {
  const { t, dateTime } = useStrings();
  const client = useQueryClient();
  const [body, setBody] = useState("");
  const [internal, setInternal] = useState(false);

  const invalidate = () => {
    client.invalidateQueries({ queryKey: ["support"] });
  };

  const reply = useMutation({
    mutationFn: (input: { id: string; body: string; internal: boolean }) =>
      api.post(`/support/tickets/${input.id}/messages`, {
        body: input.body,
        is_internal: input.internal,
      }),
    onSuccess: () => {
      setBody("");
      // Cleared too. It used to stay ticked after sending, so an operator who
      // wrote one note and then typed the actual answer sent that internally
      // as well -- and the person who reported an assault got silence, while
      // the panel showed a thread that looked answered.
      setInternal(false);
      invalidate();
    },
  });

  const decide = useMutation({
    mutationFn: (input: { id: string; status: string }) =>
      api.post(`/admin/support/tickets/${input.id}/decide`, {
        status: input.status,
      }),
    onSuccess: invalidate,
  });

  if (!ticket) return null;

  return (
    <div className="card" style={{ marginBlockStart: "var(--s-4)" }}>
      <div className="row" style={{ marginBlockEnd: "var(--s-3)" }}>
        <strong><Ltr>{ticket.reference}</Ltr></strong>
        <span>{t(`ticket.category.${ticket.category_code.toLowerCase()}`)}</span>
        {ticket.is_urgent && (
          <span className="chip failed">{t("admin.support.urgent")}</span>
        )}
        <button className="small" onClick={onClose}>
          {t("common.action.close")}
        </button>
      </div>

      {reply.error && <ErrorBanner error={reply.error} />}
      {decide.error && <ErrorBanner error={decide.error} />}

      <div style={{ marginBlockEnd: "var(--s-4)" }}>
        {ticket.messages.map((message) => (
          <div
            key={message.id}
            className={message.is_internal ? "banner" : ""}
            style={{
              marginBlockEnd: "var(--s-2)",
              paddingInlineStart: message.is_internal ? undefined : "var(--s-2)",
              borderInlineStart: message.is_internal
                ? undefined
                : "2px solid var(--border)",
            }}
          >
            <div style={{ fontSize: 12, color: "var(--text-muted)" }}>
              {/* Who reported, not what else they do. Actor.role is a property
                  of the person: somebody who also drives is DRIVER even when
                  travelling as a passenger, and most drivers in Ghorband are
                  sometimes passengers. "Driver" above a complaint about a
                  driver tells an operator the wrong thing. */}
              {message.is_from_reporter === undefined
                // An API too old to send it. Fall back to the author's role
                // rather than guessing: attributing a passenger's words to
                // VELRO, or VELRO's to the passenger, is worse than a label
                // that is merely imprecise.
                ? t(`role.${message.author_role.toLowerCase()}`)
                : message.is_from_reporter
                  ? t("admin.support.reporter")
                  : t("admin.support.from_velro")}
              {" · "}
              {dateTime(message.sent_at)}
              {message.is_internal && (
                <> {" · "}<strong>{t("admin.support.internal_note")}</strong></>
              )}
            </div>
            <div style={{ whiteSpace: "pre-wrap" }}>{message.body}</div>
          </div>
        ))}
      </div>

      <textarea
        value={body}
        rows={3}
        placeholder={t("admin.support.reply_placeholder")}
        onChange={(event) => setBody(event.target.value)}
        style={{ inlineSize: "100%" }}
      />
      <label className="row" style={{ gap: "var(--s-2)", marginBlock: "var(--s-2)" }}>
        <input
          type="checkbox"
          checked={internal}
          onChange={(event) => setInternal(event.target.checked)}
        />
        <span>
          {t("admin.support.internal_note")}
          {" — "}
          <span style={{ color: "var(--text-muted)" }}>
            {t("admin.support.internal_note_hint")}
          </span>
        </span>
      </label>

      <div className="row" style={{ gap: "var(--s-2)" }}>
        <button
          className="small primary"
          disabled={reply.isPending || !body.trim()}
          onClick={() => reply.mutate({ id: ticket.id, body, internal })}
        >
          {t("admin.support.reply")}
        </button>
        {ticket.status === "OPEN" && (
          <button
            className="small"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: ticket.id, status: "IN_PROGRESS" })}
          >
            {t("admin.support.take")}
          </button>
        )}
        {ticket.status === "RESOLVED" ? (
          <button
            className="small"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: ticket.id, status: "IN_PROGRESS" })}
          >
            {t("admin.support.reopen")}
          </button>
        ) : (
          <button
            className="small"
            disabled={decide.isPending}
            onClick={() => decide.mutate({ id: ticket.id, status: "RESOLVED" })}
          >
            {t("admin.support.resolve")}
          </button>
        )}
        <button
          className="small danger"
          disabled={decide.isPending}
          onClick={() => decide.mutate({ id: ticket.id, status: "CLOSED" })}
        >
          {t("admin.support.close")}
        </button>
      </div>
    </div>
  );
}
