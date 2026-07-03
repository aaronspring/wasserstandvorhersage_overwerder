// Anzeige immer in gesetzlicher Zeit (Europe/Berlin); Datenzeiten sind UTC.
const TZ = "Europe/Berlin";

const dateTime = new Intl.DateTimeFormat("de-DE", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
});
const time = new Intl.DateTimeFormat("de-DE", {
  timeZone: TZ,
  hour: "2-digit",
  minute: "2-digit",
});
const day = new Intl.DateTimeFormat("de-DE", {
  timeZone: TZ,
  weekday: "short",
  day: "2-digit",
  month: "2-digit",
});

const weekday = new Intl.DateTimeFormat("de-DE", {
  timeZone: TZ,
  weekday: "short",
});
const dateShort = new Intl.DateTimeFormat("de-DE", {
  timeZone: TZ,
  day: "2-digit",
  month: "2-digit",
});

export const fmtDateTime = (ms: number) => dateTime.format(ms);
export const fmtTime = (ms: number) => time.format(ms);
export const fmtDay = (ms: number) => day.format(ms);
export const fmtWeekday = (ms: number) => weekday.format(ms).replace(".", "");
export const fmtDateShort = (ms: number) => dateShort.format(ms);
export const fmtCm = (v: number) => `${Math.round(v)} cm`;
