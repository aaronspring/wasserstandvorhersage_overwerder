import { useEffect, useState } from "react";

import Chart, { SERIES } from "./Chart";
import { fmtDateTime } from "./format";
import { useTheme } from "./theme";
import type { Payload } from "./types";

const DATA_URL = `${import.meta.env.BASE_URL}data.json`;

export default function App() {
  const { colors } = useTheme();
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    fetch(DATA_URL, { cache: "no-cache" })
      .then((r) => {
        if (!r.ok) throw new Error(`HTTP ${r.status}`);
        return r.json();
      })
      .then((d: Payload) => setData(d))
      .catch((e) => setError(String(e)));
  }, []);

  return (
    <div className="app">
      <header className="head">
        <h1>Wasserstandsvorhersage Overwerder</h1>
        <p className="sub">Bogen 79 · Tideelbe · km 605,3</p>
        {data && (
          <p className="updated">
            aktualisiert {fmtDateTime(Date.parse(data.generated_at))} Uhr
          </p>
        )}
      </header>

      <main className="chart-card">
        {error && (
          <div className="status">
            Daten konnten nicht geladen werden ({error}).
          </div>
        )}
        {!error && !data && <div className="status">Lade Daten …</div>}
        {data && (
          <div className="chart-box">
            <Chart data={data} colors={colors} />
          </div>
        )}
      </main>

      {data && (
        <div className="legend">
          {SERIES.filter((m) => data.series[m.key]?.length).map((m) => (
            <span className="leg-item" key={m.key}>
              <svg width="26" height="10" aria-hidden="true">
                <line
                  x1="1"
                  y1="5"
                  x2="25"
                  y2="5"
                  stroke={m.color(colors)}
                  strokeWidth={Math.max(2, m.width)}
                  strokeDasharray={m.dash}
                />
              </svg>
              {m.label.split(" (")[0]}
            </span>
          ))}
          <span className="leg-item">
            <svg width="26" height="10" aria-hidden="true">
              <line x1="13" y1="0" x2="13" y2="10" stroke={colors.now} strokeWidth="2" />
            </svg>
            jetzt
          </span>
          <span className="leg-item">
            <svg width="26" height="10" aria-hidden="true">
              <line
                x1="13"
                y1="0"
                x2="13"
                y2="10"
                stroke={colors.forecast}
                strokeWidth="1.5"
                strokeDasharray="3 3"
              />
            </svg>
            Vorhersagebeginn
          </span>
        </div>
      )}

      <footer className="foot">
        <p>
          PNP = NHN − 5,00 m · Werte in cm über Pegelnullpunkt · gesetzliche Zeit
          (Europe/Berlin)
        </p>
        <p>
          Quellen: BSH-Kurvenvorhersage (CC BY 4.0), PEGELONLINE (WSV). Interpolation
          Zollenspieker ↔ St. Pauli auf Overwerder, kalibriert am Pegel Over. Keine
          amtliche Sturmflutwarnung.
        </p>
      </footer>
    </div>
  );
}
