/**
 * Message keys, from the same JSON the backend and both apps use.
 *
 * No user-visible literal appears anywhere else in this panel. An error code
 * from the server resolves to a sentence here through exactly the mapping the
 * mobile apps apply, so the three surfaces cannot drift apart in wording.
 */
import { KABUL, shamsiFromParts } from "./calendar";
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

/** One shared empty dictionary, so a load in flight does not remount consumers. */
const EMPTY: Dictionary = {};

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
  // The dictionary is stored with the locale it was loaded for, and readiness
  // is derived from the two matching. Tracking `ready` as its own state left a
  // window where the locale had changed but the dictionary had not, so anything
  // that rendered during the load showed the previous language.
  const [loaded, setLoaded] = useState<{
    tag: LocaleTag;
    dictionary: Dictionary;
  } | null>(null);
  const ready = loaded?.tag === locale;
  const dictionary = ready ? loaded.dictionary : EMPTY;

  useEffect(() => {
    load("en").then(setFallback);
  }, []);

  useEffect(() => {
    let cancelled = false;
    load(locale).then((dictionary) => {
      // A slow load for a locale the operator has already switched away from
      // must not overwrite the one they are now looking at.
      if (!cancelled) setLoaded({ tag: locale, dictionary });
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

  // Month names come from the dictionary, never from Intl. A browser asked for
  // a Persian month name answers with the Iranian forms (ژانویه, فوریه ...);
  // Afghanistan uses the English-derived ones (جنوری, فبروری ...), and older
  // browsers may carry no non-English month data at all.
  //
  // Which calendar, though, is the point. The driver's app shows Hijri Shamsi
  // to a Dari or Pashto speaker, because that is the calendar people keep. If
  // this panel showed Gregorian, a driver phoning support to ask about "۷ سنبله"
  // would be quoting a date the operator could not find. Same moment, same
  // calendar, both screens.
  const formatDate = useCallback(
    (parts: { year: number; month: number; day: number }) => {
      if (locale === "en") {
        const name = t(`common.month.${parts.month}`);
        return `${parts.day} ${name} ${parts.year}`;
      }
      const shamsi = shamsiFromParts(parts.year, parts.month, parts.day);
      const name = t(`common.shamsi_month.${shamsi.month}`);
      return `${num(shamsi.day)} ${name} ${num(shamsi.year)}`;
    },
    [locale, num, t],
  );

  const dateTime = useCallback(
    (iso: string) => {
      const at = new Date(iso);
      if (Number.isNaN(at.getTime())) return iso;
      // Kabul time, because that is where the trips are. The timezone shift
      // stays with the platform; only the calendar and the digits are ours.
      const parts = new Intl.DateTimeFormat("en-CA", {
        timeZone: KABUL,
        year: "numeric",
        month: "2-digit",
        day: "2-digit",
        hour: "2-digit",
        minute: "2-digit",
        hour12: false,
      }).formatToParts(at);
      const part = (type: string) =>
        Number(parts.find((candidate) => candidate.type === type)?.value ?? 0);
      const time = `${num(String(part("hour")).padStart(2, "0"))}:`
        + `${num(String(part("minute")).padStart(2, "0"))}`;
      const day = formatDate({
        year: part("year"), month: part("month"), day: part("day"),
      });
      return `${day}, ${time}`;
    },
    [formatDate, num],
  );

  const date = useCallback(
    (iso: string) => {
      // A date-only string is a calendar day, not an instant. Parsing it as a
      // timestamp puts it at UTC midnight, which in Kabul (+04:30) is already
      // the same morning -- but rendering it through a timezone at all invites
      // the day to slip, so the parts are read directly.
      const parts = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
      if (!parts) return dateTime(iso);
      // Defaults only satisfy the compiler: the regex above matched, so all
      // three groups are present.
      const [, year = "0", month = "1", day = "1"] = parts;
      return formatDate({
        year: Number(year), month: Number(month), day: Number(day),
      });
    },
    [dateTime, formatDate],
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
