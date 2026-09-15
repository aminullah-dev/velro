/**
 * Message keys, from the same JSON the backend and both apps use.
 *
 * No user-visible literal appears anywhere else in this panel. An error code
 * from the server resolves to a sentence here through exactly the mapping the
 * mobile apps apply, so the three surfaces cannot drift apart in wording.
 *
 * The provider that loads the dictionaries lives in `StringsProvider.tsx`;
 * this module holds only what the pages import, and no component, so editing
 * either keeps React Fast Refresh working.
 */
import { createContext, useContext } from "react";

export type LocaleTag = "en" | "fa-AF" | "ps";

export const LOCALES: { tag: LocaleTag; label: string; rtl: boolean }[] = [
  { tag: "fa-AF", label: "دری", rtl: true },
  { tag: "ps", label: "پښتو", rtl: true },
  { tag: "en", label: "English", rtl: false },
];

export interface StringsContext {
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
  /**
   * A calendar day as its two short parts, in the reader's calendar -- for a
   * chart's day axis, where they stack and the year would only be noise.
   */
  dayMonth: (iso: string) => { day: string; month: string };
  ready: boolean;
}

/** Filled by `StringsProvider`; read through `useStrings`. */
export const Context = createContext<StringsContext | null>(null);

export function useStrings(): StringsContext {
  const context = useContext(Context);
  if (!context) throw new Error("useStrings must be used inside a StringsProvider");
  return context;
}
