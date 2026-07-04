import { useEffect, useState } from "react";

import Chart, { SERIES } from "./Chart";
import { fmtDateTime } from "./format";
import { useTheme } from "./theme";
import type { Payload, SeriesKey } from "./types";

const DATA_URL = `${import.meta.env.BASE_URL}data.json`;

export default function App() {
  const { colors } = useTheme();
  const [data, setData] = useState<Payload | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Über die Legende aus-/eingeblendete Serien.
  const [hidden, setHidden] = useState<Set<SeriesKey>>(() => new Set());
  // Top-10-Sturmflut-Marken (per Button einblendbar; Default aus, da sie weit
  // ueber Normaltiden liegen und die Skala sonst stauchen).
  const [showSurges, setShowSurges] = useState(false);
  // BSH-Sturmflut-Klassen (Sturmflut/schwere/sehr schwere) als Referenzlinien;
  // Default aus, da sie wie die Top-10 weit ueber Normaltiden liegen.
  const [showSturmflut, setShowSturmflut] = useState(false);

  const toggle = (k: SeriesKey) =>
    setHidden((prev) => {
      const next = new Set(prev);
      if (next.has(k)) next.delete(k);
      else next.add(k);
      return next;
    });

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
        <p className="sub">Tideelbe · km 605,3</p>
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
            <Chart
              data={data}
              colors={colors}
              hidden={hidden}
              showSurges={showSurges}
              showSturmflut={showSturmflut}
            />
          </div>
        )}
      </main>

      {data && (
        <div className="legend">
          {SERIES.filter((m) => data.series[m.key]?.length).map((m) => {
            const off = hidden.has(m.key);
            return (
              <button
                type="button"
                className={`leg-item leg-toggle${off ? " off" : ""}`}
                key={m.key}
                onClick={() => toggle(m.key)}
                aria-pressed={!off}
                title={off ? "Linie einblenden" : "Linie ausblenden"}
              >
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
              </button>
            );
          })}
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
          {typeof data.gelaende_cm === "number" ? (
            <span
              className="leg-item"
              title="Ab St. Pauli NN+3,0 m steht Wasser auf dem Overwerder-Gelände (auf Pegel Over übersetzt)"
            >
              <svg width="26" height="10" aria-hidden="true">
                <line
                  x1="1"
                  y1="5"
                  x2="25"
                  y2="5"
                  stroke={colors.gelaende}
                  strokeWidth="1.5"
                  strokeDasharray="6 3"
                />
              </svg>
              Wasser auf Gelände
            </span>
          ) : null}
          {data.surge_lines?.length ? (
            <button
              type="button"
              className={`leg-item leg-toggle${showSurges ? "" : " off"}`}
              onClick={() => setShowSurges((v) => !v)}
              aria-pressed={showSurges}
              title="Historische Top-10-Sturmfluten als Referenzlinien"
            >
              <svg width="26" height="10" aria-hidden="true">
                <line
                  x1="1"
                  y1="5"
                  x2="25"
                  y2="5"
                  stroke={colors.surge}
                  strokeWidth="2"
                />
              </svg>
              Top-10 Sturmfluten
            </button>
          ) : null}
          {data.sturmflut_lines?.length ? (
            <button
              type="button"
              className={`leg-item leg-toggle${showSturmflut ? "" : " off"}`}
              onClick={() => setShowSturmflut((v) => !v)}
              aria-pressed={showSturmflut}
              title="BSH-Sturmflut-Klassen (Sturmflut, schwere, sehr schwere) als Referenzlinien, auf Pegel Over übersetzt"
            >
              <svg width="26" height="10" aria-hidden="true">
                <line
                  x1="1"
                  y1="5"
                  x2="25"
                  y2="5"
                  stroke={colors.sturmflut}
                  strokeWidth="1.5"
                  strokeDasharray="6 3"
                />
              </svg>
              Sturmflut-Stufen
            </button>
          ) : null}
          {data.surge_doc_url && (
            <a
              className="leg-item leg-link"
              href={data.surge_doc_url}
              target="_blank"
              rel="noopener noreferrer"
              title="Methodik und vollständige Top-10-Tabelle"
            >
              Top-10 ↗
            </a>
          )}
          {data.eda_doc_url && (
            <a
              className="leg-item leg-link"
              href={data.eda_doc_url}
              target="_blank"
              rel="noopener noreferrer"
              title="Sturmflut-Analyse: Häufigkeit, Saisonalität, Trend und wie oft Wasser auf dem Gelände steht"
            >
              Sturmflut-Analyse ↗
            </a>
          )}
          <p className="leg-hint">
            Legende antippen blendet Linien aus · „Top-10 Sturmfluten" zeigt die
            historischen Scheitel, „Sturmflut-Stufen" die BSH-Klassen · ins
            Diagramm tippen zeigt die
            Werte je Linie · ziehen zoomt hinein · Übersichtsleiste unten
            verschieben/aufziehen oder „Ganzer Zeitraum" zeigt die volle
            Vorhersage · Standardansicht: 12 h zurück und 36 h voraus
          </p>
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
        <p>Letzter Build: {fmtDateTime(Date.parse(__BUILD_TIME__))} Uhr</p>
      </footer>
    </div>
  );
}
