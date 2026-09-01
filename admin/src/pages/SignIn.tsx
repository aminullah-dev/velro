import { useState } from "react";
import { ApiError, api, session } from "../api/client";
import { LOCALES, useStrings, type LocaleTag } from "../i18n/strings";

interface SessionOut {
  user_id: string;
  access_token: string;
  refresh_token: string;
  roles: string[];
}

const STAFF_ROLES = new Set([
  "SUPER_ADMIN", "ADMIN", "OPERATIONS_MANAGER",
  "DISPATCHER", "FINANCE_MANAGER", "SUPPORT_AGENT",
]);

/** Staff sign-in. Same phone + OTP flow as the apps; no second credential system. */
export function SignInPage({ onSignedIn }: { onSignedIn: () => void }) {
  const { t, locale, setLocale, forErrorCode } = useStrings();
  const [step, setStep] = useState<"phone" | "code">("phone");
  const [phone, setPhone] = useState("");
  const [code, setCode] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<ApiError | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  async function requestCode() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<{ debug_code: string | null }>("/auth/otp/request", {
        phone,
        locale,
        // The console asks as itself. The server answers the same way for any
        // number, but only actually sends to one that already holds a staff
        // role -- so a stranger guessing numbers here costs nothing and
        // learns nothing.
        audience: "staff",
      });
      setStep("code");
      // Development builds echo the code so a developer with no SMS gateway
      // can still sign in; in production this is null.
      if (result.debug_code) setCode(result.debug_code);
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("INTERNAL_ERROR", 0));
    } finally {
      setBusy(false);
    }
  }

  async function verify() {
    setBusy(true);
    setError(null);
    try {
      const result = await api.post<SessionOut>("/auth/otp/verify", { phone, code, locale });
      const isStaff = result.roles.some((role) => STAFF_ROLES.has(role));
      if (!isStaff) {
        // A passenger's credentials are valid; they simply have no business
        // here. Saying so beats an empty dashboard full of 403s.
        setNotice(forErrorCode("PERMISSION_DENIED"));
        setBusy(false);
        return;
      }
      session.save(result.access_token, result.refresh_token);
      onSignedIn();
    } catch (caught) {
      setError(caught instanceof ApiError ? caught : new ApiError("INTERNAL_ERROR", 0));
      if (caught instanceof ApiError && caught.code === "OTP_INVALID") setCode("");
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="signin">
      <div className="card">
        <div className="brand">{t("app.name")}</div>

        <div className="lang-row">
          {LOCALES.map((entry) => (
            <button
              key={entry.tag}
              className={`small${entry.tag === locale ? " on" : ""}`}
              onClick={() => setLocale(entry.tag as LocaleTag)}
            >
              {entry.label}
            </button>
          ))}
        </div>

        <h1 className="page-title" style={{ fontSize: 18, marginBottom: "var(--s-5)" }}>
          {t("admin.signin.title")}
        </h1>

        {error && <div className="banner error">{forErrorCode(error.code, error.context)}</div>}
        {notice && <div className="banner error">{notice}</div>}

        {step === "phone" ? (
          <>
            <label className="field">
              <span>{t("auth.field.phone")}</span>
              {/* A phone number is always laid out left to right, even here. */}
              <input
                className="ltr"
                value={phone}
                placeholder="0700 000 001"
                inputMode="tel"
                onChange={(event) => setPhone(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && requestCode()}
              />
            </label>
            <button
              className="primary"
              style={{ width: "100%" }}
              disabled={busy || phone.replace(/\D/g, "").length < 9}
              onClick={requestCode}
            >
              {t("auth.action.send_code")}
            </button>
          </>
        ) : (
          <>
            <label className="field">
              <span>{t("auth.field.code")}</span>
              <input
                className="ltr"
                value={code}
                inputMode="numeric"
                onChange={(event) => setCode(event.target.value)}
                onKeyDown={(event) => event.key === "Enter" && verify()}
              />
            </label>
            <button
              className="primary"
              style={{ width: "100%" }}
              disabled={busy || code.length < 4}
              onClick={verify}
            >
              {t("auth.action.sign_in")}
            </button>
            <button
              style={{ width: "100%", marginTop: "var(--s-2)" }}
              onClick={() => {
                setStep("phone");
                setCode("");
                setError(null);
              }}
            >
              {t("common.action.back")}
            </button>
          </>
        )}
      </div>
    </div>
  );
}
