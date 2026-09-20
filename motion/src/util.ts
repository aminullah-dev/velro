// Western digits → Persian/Dari digits (۰۱۲۳۴۵۶۷۸۹). Used for counters.
export const toFa = (n: number | string): string =>
  String(n).replace(/\d/g, (d) => '۰۱۲۳۴۵۶۷۸۹'[Number(d)]);
