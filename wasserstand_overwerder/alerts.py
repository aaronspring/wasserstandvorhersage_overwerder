"""Alarm-Logik: aus der Overwerder-Vorhersage Gelände-/Sturmflut-Events ableiten
und mit offenen GitHub-Issues abgleichen (netzfrei, testbar).

Diese Datei enthält keine Netz-Aufrufe. Sie erkennt in der interpolierten
Overwerder-Vorhersage (cm über PNP) die vorhergesagten Tidehochwasser über der
Marke "Wasser auf Gelände", fasst sie zu Stürmen zusammen (36-h-Cluster) und
plant daraus die nötigen Issue-Aktionen. Der eigentliche GitHub-Verkehr steckt
in :mod:`wasserstand_overwerder.ghissues`, die Orchestrierung in
``alert_issues.py``.

Konventionen wie im übrigen Repo: cm über PNP, Zeitindizes tz-aware UTC, lokale
Ausgabe in Europe/Berlin.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, replace

import pandas as pd

from . import sturmflut

#: Label, an dem die Alarm-Issues erkannt werden.
LABEL = "wasserstand-alert"
#: Prefix des maschinenlesbaren Zustands-Markers im Issue-Body.
MARKER_PREFIX = "wasserstand-alert-state:"
#: Cluster-Abstand: Scheitel < GAP auseinander gehören zu einem Sturm/Event.
GAP = "36h"
#: Toleranz, mit der sich zwei Event-Zeitfenster überlappen dürfen, um als
#: dasselbe Event (Lauf-übergreifend) zu gelten.
OVERLAP_TOL = "6h"
#: Hysterese-Band (cm) gegen Zappeln an einer Schwelle bei stündlichen Läufen.
#: Eröffnet wird exakt an der Marke; geschlossen/herabgestuft erst, wenn der
#: Scheitel die Schwelle um HYSTERESE_CM klar unterschreitet, höhergestuft erst,
#: wenn er sie um HYSTERESE_CM klar überschreitet. So erzeugt eine Vorhersage,
#: die knapp um eine Grenze pendelt, nicht Lauf für Lauf neue Issues/Kommentare.
HYSTERESE_CM = 5.0


@dataclass(frozen=True)
class Event:
    """Ein vorhergesagtes Überflutungs-Event (Sturm-Cluster über der Gelände-Marke).

    Alle Zeiten tz-aware UTC, ``peak_cm`` in cm über PNP, ``stufe`` die höchste
    erreichte Stufe aus :data:`sturmflut.STUFEN` (inkl. ``"Wasser auf Gelände"``).
    """

    start: pd.Timestamp
    end: pd.Timestamp
    peak_time: pd.Timestamp
    peak_cm: float
    stufe: str


@dataclass(frozen=True)
class OpenIssue:
    """Aus einem offenen Alarm-Issue geparster Zustand (aus dem Body-Marker)."""

    number: int
    start: pd.Timestamp
    end: pd.Timestamp
    peak_time: pd.Timestamp
    stufe: str


@dataclass(frozen=True)
class PlannedAction:
    """Eine geplante Issue-Aktion.

    ``kind``: ``"create"`` (neues Issue), ``"change"`` (Stufe hat sich geändert,
    Kommentar + Marker-Update), ``"touch"`` (unverändert, nur Marker/Fenster
    aktualisieren), ``"retract"`` (Event nicht mehr auf Gelände vorhergesagt ->
    Entwarnung + schließen), ``"passed"`` (Scheitel liegt in der Vergangenheit,
    kein künftiger Scheitel mehr -> schließen).
    """

    kind: str
    number: int | None = None
    event: Event | None = None
    prev_stufe: str | None = None
    tag: bool = False


# --- Einlesen aus data.json --------------------------------------------------


def thresholds_from_payload(data: dict) -> dict[str, float]:
    """Stufen-Schwellen (cm über PNP) aus einem data.json-Dict.

    Nimmt die Gelände-Marke (``gelaende_cm``) und die BSH-Stufen
    (``sturmflut_lines``), so wie sie das Frontend erhält. Ergebnis passt zur
    Reihenfolge :data:`sturmflut.STUFEN`.
    """
    thresholds: dict[str, float] = {}
    if data.get("gelaende_cm") is not None:
        thresholds["Wasser auf Gelände"] = float(data["gelaende_cm"])
    for line in data.get("sturmflut_lines", []):
        thresholds[line["stufe"]] = float(line["cm"])
    return thresholds


def series_from_payload(data: dict, key: str = "overwerder") -> pd.Series:
    """Die Overwerder-Vorhersage aus data.json als tz-aware UTC-Serie (cm)."""
    pairs = data.get("series", {}).get(key, [])
    if not pairs:
        return pd.Series(dtype=float)
    idx = pd.to_datetime([p[0] for p in pairs], utc=True)
    vals = [float(p[1]) for p in pairs]
    return pd.Series(vals, index=idx).sort_index()


# --- Event-Erkennung ---------------------------------------------------------


def detect_events(
    target: pd.Series,
    now: pd.Timestamp,
    thresholds: dict[str, float],
    *,
    gap: str = GAP,
    hysterese_cm: float = HYSTERESE_CM,
) -> list[Event]:
    """Vorhergesagte Gelände-/Sturmflut-Events aus der Overwerder-Kurve.

    Nutzt :func:`sturmflut.tidal_highs`, betrachtet nur künftige Scheitel
    (``index >= now``) und fasst Scheitel, die weniger als ``gap``
    auseinanderliegen, zu einem Event zusammen.

    Erkannt wird bereits ab ``Gelände-Marke − hysterese_cm`` (Halte-Schwelle),
    damit ein knapp unter die Marke fallender Scheitel ein laufendes Event am
    Leben hält (kein Zappeln). ``stufe`` bleibt die echte Klassifikation des
    Scheitels und ist ``None``, wenn er die Marke selbst nicht erreicht; das
    Eröffnen an der echten Marke entscheidet :func:`plan`.
    """
    floor = thresholds.get("Wasser auf Gelände")
    if floor is None or target is None or len(target) == 0:
        return []
    keep_alive = floor - hysterese_cm
    highs = sturmflut.tidal_highs(target)
    future = highs[(highs.index >= now) & (highs >= keep_alive)].sort_index()
    if future.empty:
        return []

    limit = pd.Timedelta(gap)
    events: list[Event] = []
    times: list[pd.Timestamp] = []
    vals: list[float] = []

    def flush() -> None:
        s = pd.Series(vals, index=pd.DatetimeIndex(times))
        peak_cm = float(s.max())
        events.append(
            Event(
                start=s.index.min(),
                end=s.index.max(),
                peak_time=s.idxmax(),
                peak_cm=peak_cm,
                stufe=sturmflut.classify_level(peak_cm, thresholds),
            )
        )

    prev: pd.Timestamp | None = None
    for t, v in future.items():
        if prev is not None and (t - prev) > limit:
            flush()
            times, vals = [], []
        times.append(t)
        vals.append(float(v))
        prev = t
    if times:
        flush()
    return events


# --- Marker (maschinenlesbarer Zustand im Issue-Body) ------------------------


def render_marker(event: Event) -> str:
    """HTML-Kommentar-Marker mit dem Event-Zustand fuer den Issue-Body."""
    payload = {
        "start": event.start.isoformat(),
        "end": event.end.isoformat(),
        "peak_time": event.peak_time.isoformat(),
        "peak_cm": round(event.peak_cm, 1),
        "stufe": event.stufe,
    }
    return f"<!-- {MARKER_PREFIX}{json.dumps(payload, ensure_ascii=False)} -->"


def parse_open_issue(number: int, body: str | None) -> OpenIssue | None:
    """Zustand aus dem Body-Marker eines offenen Issues lesen (oder ``None``)."""
    if not body or MARKER_PREFIX not in body:
        return None
    start = body.index(MARKER_PREFIX) + len(MARKER_PREFIX)
    end = body.find("-->", start)
    if end == -1:  # Marker ohne schliessendes "-->": unbrauchbar, aber kein Crash
        return None
    try:
        data = json.loads(body[start:end].strip())
        return OpenIssue(
            number=number,
            start=pd.Timestamp(data["start"]),
            end=pd.Timestamp(data["end"]),
            peak_time=pd.Timestamp(data["peak_time"]),
            stufe=str(data["stufe"]),
        )
    except (KeyError, ValueError, json.JSONDecodeError):
        return None


# --- Abgleich Events <-> offene Issues ---------------------------------------


def _overlaps(a: OpenIssue | Event, b: OpenIssue | Event, tol: pd.Timedelta) -> bool:
    return max(a.start, b.start) <= min(a.end, b.end) + tol


def sticky_stufe(
    prev_stufe: str,
    peak_cm: float,
    thresholds: dict[str, float],
    hysterese_cm: float = HYSTERESE_CM,
) -> str | None:
    """Stufe eines laufenden Events mit Hysterese gegen Grenz-Zappeln.

    Ausgehend von ``prev_stufe`` wird nur dann höhergestuft, wenn ``peak_cm`` die
    nächste Schwelle um ``hysterese_cm`` überschreitet, und nur dann herabgestuft,
    wenn er die aktuelle Schwelle um ``hysterese_cm`` unterschreitet. ``None``
    heißt: unter die Gelände-Marke (minus Band) gefallen. Reihenfolge:
    :data:`sturmflut.STUFEN`.
    """
    order = [s for s in sturmflut.STUFEN if s in thresholds]
    if prev_stufe not in order:  # unbekannt: frische Klassifikation
        return sturmflut.classify_level(peak_cm, thresholds)
    i = order.index(prev_stufe)
    while i + 1 < len(order) and peak_cm >= thresholds[order[i + 1]] + hysterese_cm:
        i += 1
    while i >= 0 and peak_cm < thresholds[order[i]] - hysterese_cm:
        i -= 1
    return order[i] if i >= 0 else None


def plan(
    events: list[Event],
    issues: list[OpenIssue],
    now: pd.Timestamp,
    thresholds: dict[str, float],
    *,
    overlap_tol: str = OVERLAP_TOL,
    hysterese_cm: float = HYSTERESE_CM,
) -> list[PlannedAction]:
    """Aktionen ableiten: neue Issues, Stufen-Kommentare, Entwarnungen.

    Jedes Event wird über Zeitfenster-Überlappung höchstens einem offenen Issue
    zugeordnet (ein Issue pro Sturm). Eröffnet wird nur an der echten Gelände-
    Marke (Events im Halte-Band ohne Treffer werden ignoriert); die Stufe eines
    laufenden Events folgt der Hysterese (:func:`sticky_stufe`), sodass eine um
    eine Grenze pendelnde Vorhersage keine wechselnden Kommentare erzeugt. Offene
    Issues ohne aktuelles (Halte-)Event werden entwarnt (künftig, aber klar unter
    der Marke) bzw. als vorbei geschlossen (Scheitel bereits vergangen).
    """
    tol = pd.Timedelta(overlap_tol)
    actions: list[PlannedAction] = []
    used: set[int] = set()

    for event in events:
        match = next(
            (
                iss
                for iss in issues
                if iss.number not in used and _overlaps(event, iss, tol)
            ),
            None,
        )
        if match is None:
            # Neues Issue nur, wenn der Scheitel die echte Gelände-Marke erreicht;
            # Scheitel bloß im Halte-Band (stufe None) eröffnen nichts.
            if event.stufe is not None:
                actions.append(PlannedAction("create", event=event, tag=True))
            continue
        used.add(match.number)
        stufe = sticky_stufe(match.stufe, event.peak_cm, thresholds, hysterese_cm)
        event = replace(event, stufe=stufe or match.stufe)
        if event.stufe != match.stufe:
            actions.append(
                PlannedAction(
                    "change",
                    number=match.number,
                    event=event,
                    prev_stufe=match.stufe,
                    tag=True,
                )
            )
        else:
            actions.append(
                PlannedAction(
                    "touch",
                    number=match.number,
                    event=event,
                    prev_stufe=match.stufe,
                )
            )

    for iss in issues:
        if iss.number in used:
            continue
        if iss.peak_time >= now:
            # Vorhersage nimmt das Event von der Gelände-Marke zurück -> Entwarnung.
            actions.append(
                PlannedAction(
                    "retract", number=iss.number, prev_stufe=iss.stufe, tag=True
                )
            )
        else:
            # Scheitel liegt in der Vergangenheit, kein künftiger mehr -> vorbei.
            actions.append(
                PlannedAction("passed", number=iss.number, prev_stufe=iss.stufe)
            )
    return actions


# --- Rendering von Titel/Body/Kommentaren ------------------------------------

TZ = "Europe/Berlin"


def fmt_local(ts: pd.Timestamp) -> str:
    """Zeit in gesetzlicher Zeit (Europe/Berlin) als ``TT.MM.JJJJ HH:MM``."""
    return ts.tz_convert(TZ).strftime("%d.%m.%Y %H:%M")


def _height_line(event: Event, gauge_zero_m_nhn: float | None) -> str:
    pnp = f"{event.peak_cm:.0f} cm über PNP"
    if gauge_zero_m_nhn is not None:
        nhn = event.peak_cm / 100.0 + gauge_zero_m_nhn
        return f"{pnp} (≈ NHN {nhn:+.2f} m)"
    return pnp


def issue_title(event: Event) -> str:
    """Kurzer Issue-Titel mit höchster Stufe und lokalem Scheiteltag."""
    day = fmt_local(event.peak_time)[:10]
    return f"⚠️ Overwerder: {event.stufe} vorhergesagt am {day}"


def issue_body(
    event: Event, mention: str, *, gauge_zero_m_nhn: float | None = None
) -> str:
    """Issue-Body mit Erwähnung, Kennzahlen und maschinenlesbarem Marker."""
    lines = [
        f"@{mention} — für **Overwerder** ist **Wasser auf dem Gelände** vorhergesagt.",
        "",
        f"- **Höchste Stufe:** {event.stufe}",
        f"- **Scheitel:** {fmt_local(event.peak_time)} (gesetzliche Zeit)",
        f"- **Höhe:** {_height_line(event, gauge_zero_m_nhn)}",
        f"- **Event-Fenster:** {fmt_local(event.start)} – {fmt_local(event.end)}",
        "",
        "Ein Issue pro vorhergesagtem Event. Bei jeder Stufen-Änderung oder der "
        "Entwarnung folgt ein Kommentar.",
        "",
        render_marker(event),
    ]
    return "\n".join(lines)


def change_comment(
    event: Event,
    prev_stufe: str | None,
    mention: str,
    *,
    gauge_zero_m_nhn: float | None = None,
) -> str:
    """Kommentar bei geänderter Stufe (mit erneuter Erwähnung)."""
    prev = prev_stufe or "unbekannt"
    higher = _rank(event.stufe) > _rank(prev_stufe)
    verb = "Höherstufung" if higher else "Herabstufung"
    return "\n".join(
        [
            f"@{mention} — **{verb}:** {prev} → **{event.stufe}**.",
            "",
            f"- **Neuer Scheitel:** {fmt_local(event.peak_time)} "
            f"({_height_line(event, gauge_zero_m_nhn)})",
        ]
    )


def retract_comment(mention: str) -> str:
    """Kommentar bei Entwarnung (Event nicht mehr auf Gelände vorhergesagt)."""
    return (
        f"@{mention} — **Entwarnung:** Für dieses Event wird **kein Wasser auf dem "
        f"Gelände** mehr vorhergesagt. Issue wird geschlossen."
    )


def passed_comment() -> str:
    """Kommentar, wenn der Scheitel vorbei ist (kein künftiger mehr)."""
    return (
        "Der vorhergesagte Scheitel liegt in der Vergangenheit. Issue wird geschlossen."
    )


def _rank(stufe: str | None) -> int:
    """Index der Stufe in :data:`sturmflut.STUFEN` (-1, falls unbekannt)."""
    if stufe in sturmflut.STUFEN:
        return sturmflut.STUFEN.index(stufe)
    return -1
