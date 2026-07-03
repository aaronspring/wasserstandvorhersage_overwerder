import { useEffect, useState } from "react";

export interface Colors {
  ink: string;
  secondary: string;
  muted: string;
  grid: string;
  axis: string;
  overwerder: string;
  over: string;
  gray: string;
  now: string;
  forecast: string;
  ref: string;
  tooltipBg: string;
}

// Farbrollen aus der dataviz-Referenzpalette, je Modus fuer die Chart-Flaeche
// gestuft. Overwerder = Blau (Hauptserie), Over = Tinte (Messung), Stuetzpegel
// gedaempftes Grau (per Strichmuster unterschieden), "jetzt" = Orange.
const LIGHT: Colors = {
  ink: "#0b0b0b",
  secondary: "#52514e",
  muted: "#898781",
  grid: "#e1e0d9",
  axis: "#c3c2b7",
  overwerder: "#2a78d6",
  over: "#0b0b0b",
  gray: "#898781",
  now: "#eb6834",
  forecast: "#52514e",
  ref: "#a3a199",
  tooltipBg: "#fffffff2",
};

const DARK: Colors = {
  ink: "#ffffff",
  secondary: "#c3c2b7",
  muted: "#898781",
  grid: "#2c2c2a",
  axis: "#383835",
  overwerder: "#3987e5",
  over: "#ffffff",
  gray: "#b0aea6",
  now: "#d95926",
  forecast: "#c3c2b7",
  ref: "#77756f",
  tooltipBg: "#1f1f1ef2",
};

function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(
    () => window.matchMedia?.(query).matches ?? false,
  );
  useEffect(() => {
    const mq = window.matchMedia(query);
    const onChange = (e: MediaQueryListEvent) => setMatches(e.matches);
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, [query]);
  return matches;
}

export const useNarrow = () => useMediaQuery("(max-width: 560px)");

export function useTheme(): { mode: "light" | "dark"; colors: Colors } {
  const dark = useMediaQuery("(prefers-color-scheme: dark)");
  return { mode: dark ? "dark" : "light", colors: dark ? DARK : LIGHT };
}
