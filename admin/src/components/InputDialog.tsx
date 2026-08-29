import { useEffect, useRef, useState } from "react";
import { useStrings } from "../i18n/strings";

/**
 * Ask for one value before something irreversible.
 *
 * Replaces `window.prompt`, which several browsers suppress in embedded and
 * sandboxed contexts -- there the operator sees nothing at all and the action
 * silently does not happen. A native `<dialog>` also gives focus trapping,
 * Escape to dismiss and a backdrop for free, which a prompt does not.
 *
 * The reason is not decoration: a driver refused a payout or taken off the road
 * is owed an explanation, and it is what the audit entry records.
 */
export function InputDialog({
  open,
  titleKey,
  confirmKey,
  hintKey,
  labelKey = "admin.action.reason",
  field = "text",
  initialValue = "",
  required = true,
  destructive = true,
  onConfirm,
  onCancel,
}: {
  open: boolean;
  titleKey: string;
  confirmKey: string;
  hintKey?: string;
  labelKey?: string;
  /**
   * A date gets a real date input and a number a numeric one: free text for
   * either is a format argument the operator loses.
   */
  field?: "text" | "date" | "number";
  /** Prefilled, so changing a price starts from the current one. */
  initialValue?: string;
  /** An expiry may legitimately be blank; a refusal reason may not. */
  required?: boolean;
  destructive?: boolean;
  onConfirm: (value: string) => void;
  onCancel: () => void;
}) {
  const { t } = useStrings();
  const ref = useRef<HTMLDialogElement>(null);
  const [reason, setReason] = useState("");

  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    if (open && !dialog.open) {
      setReason(initialValue);
      // showModal, not show: it traps focus and makes the rest inert, so Tab
      // cannot wander behind the dialog into the table underneath.
      dialog.showModal();
    } else if (!open && dialog.open) {
      dialog.close();
    }
  }, [open, initialValue]);

  if (!open) return null;

  const trimmed = reason.trim();
  // A number must actually be one. Rejecting it silently -- which is what the
  // prompt this replaced did -- leaves an operator tapping a button that
  // appears to do nothing at all.
  const numberProblem =
    field === "number" &&
    trimmed !== "" &&
    !(Number.isFinite(Number(trimmed)) && Number(trimmed) >= 0);
  const satisfied = (!required || trimmed.length > 0) && !numberProblem;

  return (
    <dialog
      ref={ref}
      className="reason-dialog"
      // Escape and the backdrop both cancel, which is what a dismiss gesture
      // must never be allowed to mean "confirm".
      onCancel={(event) => {
        event.preventDefault();
        onCancel();
      }}
    >
      <form
        method="dialog"
        onSubmit={(event) => {
          event.preventDefault();
          if (satisfied) onConfirm(trimmed);
        }}
      >
        <h3>{t(titleKey)}</h3>
        {/* A visible label, not a placeholder: a placeholder disappears the
            moment someone starts typing, taking the question with it. */}
        <label htmlFor="reason-field">{t(labelKey)}</label>
        {field === "date" ? (
          <input
            id="reason-field"
            type="date"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            autoFocus
          />
        ) : field === "number" ? (
          <input
            id="reason-field"
            type="number"
            inputMode="decimal"
            min="0"
            step="0.01"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            autoFocus
          />
        ) : (
          <textarea
            id="reason-field"
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            autoFocus
            maxLength={500}
          />
        )}
        {/* Persistent helper text, below the field. An operator should not have
            to remember the rule from a sentence that has already gone. */}
        {numberProblem ? (
          // The error sits with the field it is about, not at the top of a
          // dialog the operator has already read past.
          <p className="hint error" role="alert">{t("admin.error.not_a_number")}</p>
        ) : (
          hintKey && <p className="hint">{t(hintKey)}</p>
        )}
        <div className="row" style={{ gap: "var(--s-2)", justifyContent: "flex-end" }}>
          <button type="button" onClick={onCancel}>
            {t("common.action.cancel")}
          </button>
          <button
            type="submit"
            className={destructive ? "danger" : "primary"}
            // Refused here rather than by the server, so the operator is not
            // told after the fact that what they typed did not count.
            disabled={!satisfied}
          >
            {t(confirmKey)}
          </button>
        </div>
      </form>
    </dialog>
  );
}
