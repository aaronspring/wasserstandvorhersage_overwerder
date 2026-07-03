export type Point = [string, number];

export type SeriesKey = "overwerder" | "over" | "zollenspieker" | "st_pauli";

export interface Payload {
  generated_at: string;
  now: string;
  forecast_start: string;
  units: string;
  gauge_zero_m_nhn: number | null;
  hours_back: number;
  reference_lines: Record<string, number>;
  series: Partial<Record<SeriesKey, Point[]>>;
}
