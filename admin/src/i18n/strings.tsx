/**
 * Message keys, from the same JSON the backend and both apps use.
 *
 * No user-visible literal appears anywhere else in this panel. An error code
 * from the server resolves to a sentence here through exactly the mapping the
 * mobile apps apply, so the three surfaces cannot drift apart in wording.
 */
import {
  createContext, useCallback, useContext, useEffect, useMemo, useState,
  type ReactNode,
} from "react";

export type LocaleTag = "en" | "fa-AF" | "ps";

export const LOCALES: { tag: LocaleTag; label: string; rtl: boolean }[] = [
  { tag: "fa-AF", label: "دری", rtl: true },
  { tag: "ps", label: "پښتو", rtl: true },
  { tag: "en", label: "English", rtl: false },
];

const EASTERN = "۰۱۲۳۴۵۶۷۸۹";
const PLACEHOLDER = /\{(\w+)\}/g;
const STORAGE_KEY = "velro.locale";

type Dictionary = Record<string, string>;

interface StringsContext {
  locale: LocaleTag;
  rtl: boolean;
  setLocale: (tag: LocaleTag) => void;
  t: (key: string, params?: Record<string, unknown>) => string;
  forErrorCode: (code: string, context?: Record<string, unknown>) => string;
  /** Eastern Arabic-Indic digits for Dari and Pashto prose. */
  num: (value: number | string) => string;
  money: (amountMinor: number, currency?: string) => string;
  dateTime: (iso: string) => string;
  /** A calendar day with no time: a settlement period, an expiry, a birthday. */
  date: (iso: string) => string;
  ready: boolean;
}

const Context = createContext<StringsContext | null>(null);

async function load(tag: LocaleTag): Promise<Dictionary> {
  try {
    const response = await fetch(`/locales/${tag}.json`);
    if (!response.ok) return {};
    return (await response.json()) as Dictionary;
  } catch {
    return {};
  }
}

export function StringsProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<LocaleTag>(
    () => (localStorage.getItem(STORAGE_KEY) as LocaleTag | null) ?? "fa-AF",
  );
  // English is the fallback because it is the only file guaranteed complete.
  const [fallback, setFallback] = useState<Dictionary>({});
  const [dictionary, setDictionary] = useState<Dictionary>({});
  const [ready, setReady] = useState(false);

  useEffect(() => {
    load("en").then(setFallback);
  }, []);

  useEffect(() => {
    let cancelled = false;
    setReady(false);
    load(locale).then((loaded) => {
      if (cancelled) return;
      setDictionary(loaded);
      setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, [locale]);

  const rtl = useMemo(
    () => LOCALES.find((entry) => entry.tag === locale)?.rtl ?? true,
    [locale],
  );

  useEffect(() => {
    // Direction follows the chosen locale, not the browser's, so a Dari
    // operator on an English machine still gets an RTL panel.
    document.documentElement.lang = locale;
    document.documentElement.dir = rtl ? "rtl" : "ltr";
  }, [locale, rtl]);

  const num = useCallback(
    (value: number | string) => {
      const text = String(value);
      if (!rtl) return text;
      return text.replace(/[0-9]/g, (digit) => EASTERN[Number(digit)]!);
    },
    [rtl],
  );

  const t = useCallback(
    (key: string, params?: Record<string, unknown>) => {
      const template = dictionary[key] ?? fallback[key];
      // An unknown key shows as the key itself: an obvious bug report, where a
      // blank space would be a mystery.
      if (template === undefined) return key;
      if (!params) return template;
      return template.replace(PLACEHOLDER, (match, name: string) => {
        const value = params[name];
        if (value === undefined || value === null) return match;
        return typeof value === "number" ? num(value) : String(value);
      });
    },
    [dictionary, fallback, num],
  );

  const forErrorCode = useCallback(
    (code: string, context?: Record<string, unknown>) => {
      const key = `error.${code.toLowerCase()}`;
      const resolved = t(key, context);
      // A code with no translation must never reach an operator raw.
      return resolved === key ? t("error.internal_error") : resolved;
    },
    [t],
  );

  const money = useCallback(
    (amountMinor: number, currency = "AFN") => {
      // Integer minor units in, formatted string out. The division happens
      // here, at the display boundary, and nowhere else.
      const major = amountMinor / 100;
      const grouped = major.toLocaleString("en-US", {
        minimumFractionDigits: Number.isInteger(major) ? 0 : 2,
        maximumFractionDigits: 2,
      });
      // The label is per-currency; an unknown code prints as itself rather than
      // being silently labelled as afghanis.
      const labelKey = `common.label.currency_${currency.toLowerCase()}`;
      const label = t(labelKey);
      return `${num(grouped)} ${label === labelKey ? currency : label}`;
    },
    [num, t],
  );

  const dateTime = useCallback(
    (iso: string) => {
      const at = new Date(iso);
      if (Number.isNaN(at.getTime())) return iso;
      // Kabul time, because that is where the trips are.
      const rendered = at.toLocaleString(locale === "en" ? "en-GB" : "en-GB", {
        timeZone: "Asia/Kabul",
        day: "2-digit",
        month: "short",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      });
      return num(rendered);
    },
    [locale, num],
  );

  const date = useCallback(
    (iso: string) => {
      // A date-only string is a calendar day, not an instant. Parsing it as a
      // timestamp puts it at UTC midnight, which in Kabul (+04:30) is already
      // the same morning -- but rendering it through a timezone at all invites
      // the day to slip, so the parts are read directly.
      const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
      if (!parts) return dateTime(iso);
      const [, year, month, day] = parts;
      const rendered = new Date(
        Number(year), Number(month) - 1, Number(day),
      ).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric" });
      return num(rendered);
    },
    [dateTime, num],
  );

  const setLocale = useCallback((tag: LocaleTag) => {
    localStorage.setItem(STORAGE_KEY, tag);
    setLocaleState(tag);
  }, []);

  const value = useMemo<StringsContext>(
    () => ({
      locale, rtl, setLocale, t, forErrorCode, num, money, dateTime, date, ready,
    }),
    [locale, rtl, setLocale, t, forErrorCode, num, money, dateTime, date, ready],
  );

  return <Context.Provider value={value}>{children}</Context.Provider>;
}

export function useStrings(): StringsContext {
  const context = useContext(Context);
  if (!context) throw new Error("useStrings must be used inside a StringsProvider");
  return context;
}
