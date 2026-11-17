"""Statische Konfiguration: Orte, Stationsnamen, Modell-Defaults."""

# Elbe-Kilometrierung (km waechst stromab)
ELBE_KM = {
    "zollenspieker": 598.3,
    "over": 605.3,  # Messpegel direkt gegenueber Overwerder
    "overwerder": 605.3,  # Zielort: Overwerder
    "st_pauli": 623.1,
}

# PEGELONLINE-Stationsnamen (REST-API v2, Zeitreihe "W" in cm ueber PNP)
PEGELONLINE_BASE = "https://www.pegelonline.wsv.de/webservices/rest-api/v2"
PEGELONLINE_STATIONS = {
    "zollenspieker": "ZOLLENSPIEKER",
    "st_pauli": "HAMBURG ST. PAULI",
    "over": "OVER",
}

# PEGELONLINE-Langzeitarchiv ("Download langfristiger Wasserstaende (Rohdaten)
# ab dem 1.1.2000"): minuetliche, ungeprueft Rohdaten seit 2000-01-01 als
# ZIP mit CSV (timestamp;value). Zeitstempel in gesetzlicher Zeit (MEZ/MESZ),
# Werte in cm ueber PNP. Nur fuer WSV-Pegel verfuegbar; HPA-Pegel wie
# HAMBURG ST. PAULI sind NICHT im Archiv (nur rollierende 31 Tage per REST).
PEGELONLINE_WEB_BASE = "https://pegelonline.wsv.de/gast"
PEGELONLINE_HISTORY_PARAMETER = "W"
# Stations-UUIDs (identisch mit REST-API-v2-"uuid") fuer das Langzeitarchiv.
PEGELONLINE_STATION_UUIDS = {
    "zollenspieker": "3de8ea26-ab29-4e46-adad-06198ba2e0b7",
    "over": "b02ce5c0-64e9-4d24-90b9-269a28a1e9f9",
    "st_pauli": "d488c5cc-4de9-4631-8ce1-0db0e700b546",
}
# Zeitzone der gesetzlichen Zeit in den Archiv-CSV (MEZ/MESZ mit Sommerzeit).
PEGELONLINE_HISTORY_TZ = "Europe/Berlin"
# Pegel mit Langzeitarchiv (WSV). HPA-Pegel wie st_pauli haben keins und
# liefern nur die rollierenden 31 Tage der REST-API.
PEGELONLINE_ARCHIVE_STATIONS = ("zollenspieker", "over")
# Hugging-Face-Dataset, in dem das Parquet-Archiv gehostet wird.
PEGELONLINE_HF_REPO = "aaronspring/elbe-pegel-over-zollenspieker-minutely-since-2000"

# BSH WaterLevelForecast (OGC API Features, CC BY 4.0)
BSH_BASE = "https://gdi.bsh.de/ldproxy/rest/services/WaterLevelForecast"
# Namensmuster, um die Stationen in den BSH-Features wiederzufinden
# (Feld-/Collectionnamen werden zur Laufzeit per Discovery ermittelt).
BSH_STATION_PATTERNS = {
    "zollenspieker": ("zollenspieker",),
    "st_pauli": ("st. pauli", "st.pauli", "st pauli", "sankt pauli"),
}
# Falls die BSH-Vorhersage nicht in cm ueber PNP kommt: hier Offset in cm
# eintragen (wert_cm_pnp = wert_roh_cm + datum_offset_cm). Mit
# `python forecast.py --explore` Rohdaten inspizieren.
BSH_DATUM_OFFSET_CM = {
    "zollenspieker": 0.0,
    "st_pauli": 0.0,
}

# --- Sturmflut-Bezugshoehen am Pegel HAMBURG ST. PAULI ----------------------
# Die amtliche BSH-Sturmflut-Klassifikation und die Overwerder-Marke "Wasser auf
# dem Gelaende" beziehen sich auf den Pegel St. Pauli, NICHT auf Over. Quelle:
# Sturmfluttafel der Siedlung Overwerder (docs/sturmfluttafel_overwerder.jpeg).
ST_PAULI_PNP_NN_M = -5.00  # PNP = NN - 5,00 m (wie bei allen Tideelbe-Pegeln)
ST_PAULI_MThw_NN_M = 2.09  # mittleres Tidehochwasser (MThw) am Pegel St. Pauli
# Marke, ab der bei Overwerder Wasser auf dem Gelaende steht (St.-Pauli-Bezug).
WASSER_AUF_GELAENDE_NN_M = 3.00
# Dieselbe Marke, auf den Pegel Over uebersetzt (cm ueber PNP). Ergebnis der
# St.-Pauli-Ausrichtung ueber Datums-Anker (sturmflut.align_to_stpauli, siehe
# docs/STURMFLUT_EDA.md). Als Referenzlinie im Web-Chart genutzt.
WASSER_AUF_GELAENDE_OVER_CM = 834.0
# BSH-Nordsee-Stufen als Aufschlag auf das St.-Pauli-MThw (m ueber MThw).
BSH_STUFEN_UEBER_MThw_M = {
    "Sturmflut": 1.5,
    "schwere Sturmflut": 2.5,
    "sehr schwere Sturmflut": 3.5,
}
# Dieselben BSH-Klassen, auf den Pegel Over uebersetzt (untere Schwelle je
# Stufe, cm ueber PNP) — analog zu WASSER_AUF_GELAENDE_OVER_CM das Ergebnis der
# St.-Pauli-Ausrichtung (sturmflut.over_thresholds, siehe docs/STURMFLUT_EDA.md).
# Als Referenzlinien im Web-Chart genutzt (Default aus, da weit ueber Normaltide).
STURMFLUT_STUFEN_OVER_CM = {
    "Sturmflut": 888.0,
    "schwere Sturmflut": 979.0,
    "sehr schwere Sturmflut": 1069.0,
}
# Datums-Anker zur Ausrichtung Over <-> St. Pauli: amtliche St.-Pauli-Scheitel
# (m ueber NN) bekannter Sturmfluten aus der Sturmfluttafel. Nur Ereignisse ab
# 2000, die auch in der Over-Langzeitreihe liegen. Zusammen mit dem MThw-Paar
# (St.-Pauli-MThw <-> Over-MThw) ergibt sich ein linearer Zusammenhang, mit dem
# die St.-Pauli-Schwellen in cm ueber PNP am Pegel Over uebersetzt werden.
ST_PAULI_ANKER_NN_M = {
    "2007-11-09": 5.65,  # Tilo
    "2013-12-06": 6.09,  # Xaver
    "2014-10-22": 4.17,  # Sturmflut Okt. 2014
}

# Plausibler Wertebereich fuer Tideelbe-Wasserstaende in cm ueber PNP
# (PNP = NHN - 5,00 m): grob 100..1100 cm. Dient der Einheiten-Pruefung.
PLAUSIBLE_CM_PNP = (50.0, 1300.0)

# GitHub-Repo mit Quellcode und Pipeline (Doku-Links, HF-Dataset-Card).
GITHUB_REPO_URL = "https://github.com/aaronspring/wasserstandvorhersage_overwerder"

# Historische Sturmflut-Scheitel am Pegel Over (cm ueber PNP), Raenge 1/3/5/10.
# Einzige Quelle fuer Plot (plot.py) und Web-Export (webexport.py); die volle
# Tabelle samt Methodik steht in docs/TOP_10_STURMFLUTEN.md.
STURMFLUT_DOC = "docs/TOP_10_STURMFLUTEN.md"
STURMFLUT_DOC_URL = f"{GITHUB_REPO_URL}/blob/main/{STURMFLUT_DOC}"
# Sturmflut-EDA (Haeufigkeit/Saison/Trend + "Wasser auf dem Gelaende"); im
# Web-Chart als Link hinter der Gelaende-Linie verknuepft.
STURMFLUT_EDA_DOC = "docs/STURMFLUT_EDA.md"
STURMFLUT_EDA_DOC_URL = f"{GITHUB_REPO_URL}/blob/main/{STURMFLUT_EDA_DOC}"
STURMFLUT_SCHEITEL_CM = {
    1: (1114, "Xaver 2013"),
    3: (1067, "Tilo 2007"),
    5: (1060, "Dez. 2023"),
    10: (1008, "Emma 2008"),
}
# Scheitelzeitpunkte dazu (gesetzliche Zeit Europe/Berlin, aus
# docs/TOP_10_STURMFLUTEN.md); fuer die Ereignis-Kurven der Overhaken-Karte
# (export_surge_events.py -> web/public/surge_events.json).
STURMFLUT_SCHEITEL_ZEIT = {
    1: "2013-12-06 06:31",
    3: "2007-11-09 15:51",
    5: "2023-12-22 11:05",
    10: "2008-03-01 19:50",
}
# Ausschnitt je Ereignis: so lange vor dem Scheitel, dass Vortiden und
# Versickerung in der Karte stimmen, und kurz danach.
SURGE_EVENT_BEFORE_H = 72
SURGE_EVENT_AFTER_H = 6

HTTP_TIMEOUT = 30  # Sekunden
USER_AGENT = "wasserstandvorhersage-overwerder/0.1 (github.com/aaronspring)"

# --- Gelaende / Ueberflutungs-Zeitpunkte (inundation.py) --------------------
# PNP des Pegels Over in m ueber NHN (PEGELONLINE gaugeZero, gueltig ab
# 2019-11-01). Nicht -5,00 wie die generische Tideelbe-Konvention: die 9,8 cm
# Unterschied verschieben den Ueberflutungsbeginn um mehrere Minuten.
OVER_PNP_NHN_M = -5.098
# DGM1 2022 (LGV Hamburg, 1-m-Raster, GeoTIFF-Kacheln 1x1 km im ZIP, 1,3 GB).
# Die alten daten-hamburg.de-Links liefern 404; das Transparenzportal verweist
# auf diese Archiv-Kopie. Datenlizenz Deutschland - Namensnennung 2.0.
DGM1_URL = (
    "https://archiv.transparenz.hamburg.de/hmbtgarchive/HMDK/"
    "dgm1_hh_2022-04-30_258334_snap_1.zip"
)
# Modellausschnitt (EPSG:25832): Overwerder Vorland zwischen Hauptdeich und
# Elbe samt Strom als Wasserquelle.
INUNDATION_BBOX = (572400.0, 5919900.0, 574800.0, 5922200.0)
# Auswerteflaeche: Huetten 100-141 des Freizeit-, Sport- und Gartenvereins
# Overhaken e. V. (zwischen Priel und Overwerder Hauptdeich, um 53.4356 N /
# 10.1067 E). Gebaeude der Web-Karte werden nur hier ausgewertet.
OVERHAKEN_BBOX = (573390.0, 5921160.0, 573600.0, 5921420.0)
# Parzellen-Nummern der Kolonie laut Lageplan-Schild am Vereinsgelaende
# (Foto Nov. 2026), je LoD2-Gebaeude ueber die ALKIS-Kennung (die laufende
# Nummer ``nr`` aendert sich, wenn Gebaeude hinzukommen). Zuordnung: rosa
# Haeuser des Plans per Farbe erkannt, affin + Thin-Plate-Spline auf die
# LoD2-Schwerpunkte gelegt (Median-Abstand ~2 m), am Luftbild geprueft. Nur
# diese Gebaeude zeigt die Web-Karte. Ohne LoD2-Gebaeude (Rasen im DOP 2024 /
# nur Schuppen): 116, 133 und je ein zweites Haus auf
# 119 und 126. Ein Gebaeude kann mehrere Parzellen tragen (102/103, 130-132);
# Schuppen (zweites Gebaeude auf 114, Garage) sind bewusst nicht eingetragen.
# 136 (Wohnwagen) fehlt in LoD2 und ist als Grundriss aus dem DOP 2024
# nachgezeichnet (OVERHAKEN_MANUELLE_GEBAEUDE). Das oestliche der beiden
# LoD2-Gebaeude auf 124 (DEHHALKAn0006JIM) ist ein Nebengebaeude -> entfaellt.
OVERHAKEN_PARZELLEN = {
    "manuell-136": "136",
    "DEHHALKAn0006IVU": "Pumpenhaus",
    "DEHHALKAn0006IAL": "101",
    "DEHHALKAn0006JGI": "102/103",
    "DEHHALKAn0006IjI": "104",
    "DEHHALKAn0006I87": "105",
    "DEHHALKAn0006HzK": "106",
    "DEHHALKAn0006I9p": "107",
    "DEHHALKAn0006HyW": "108",
    "DEHHALKAn0006I5I": "109",
    "DEHHALKAn0006Il7": "110",
    "DEHHALKAn0006Isn": "111",
    "DEHHALKAn0006JBq": "112",
    "DEHHALKAn0006J0u": "113",
    "DEHHALKAn0006I8G": "114",
    "DEHHALKAn0006IFR": "115",
    "DEHHALKAn0006IuD": "117",
    "DEHHALKAn0006JAw": "118",
    "DEHHALKAn0006J2K": "119",
    "DEHHALKAn0006Imp": "120",
    "DEHHALKAn0006IlO": "121",
    "DEHHALKAn0006JIP": "122",
    "DEHHALKAn0006I5b": "123",
    "DEHHALKAn0006ItW": "124",
    "DEHHALKAn0006JGG": "125",
    "DEHHALKAn0006IvS": "126",
    "DEHHALKAn0006IGC": "100",
    "DEHHALKAn0006J7b": "128",
    "DEHHALKAn0006JHu": "129",
    "DEHHALKAn0006Igh": "130-132",
    "DEHHALKAn0006J50": "134",
    "DEHHALKAn0006I8U": "135",
    "DEHHALKAn0006I22": "137",
    "DEHHALKAn0006IyH": "138",
    "DEHHALKAn0006Idn": "139",
    "DEHHALKAn0006JBD": "140",
    "DEHHALKAn0006Ip9": "141",
}
# Gebaeude ohne LoD2-Grundriss, aus dem Luftbild (DOP 2024) nachgezeichnet:
# Kennung -> Ecken (EPSG:25832). Bodenhoehe = tiefste DGM1-Zelle im Grundriss.
OVERHAKEN_MANUELLE_GEBAEUDE = {
    "manuell-136": (  # Wohnwagen suedlich von 137
        (573428.6, 5921319.6),
        (573431.8, 5921320.6),
        (573433.0, 5921317.4),
        (573429.8, 5921316.4),
    ),
}
# Zellen mit Ueberlaufhoehe darunter liegen stromseitig des Overwerder
# Hauptdeichs (Kronenhoehe im DGM1 >= 8 m NHN); dahinter gilt als geschuetzt.
VORLAND_MAX_SPILL_M = 7.0
# Ausschnitt der Web-Karte (EPSG:25832): Kolonie plus Elbe im Westen. Der
# Modellausschnitt (INUNDATION_BBOX) bleibt gross, damit die Wasserwege stimmen.
INUNDATION_VIEW = (573180.0, 5921080.0, 573720.0, 5921500.0)
# Beschriftungen der Web-Karte (Text, x, y).
INUNDATION_MAP_LABELS = (
    ("Elbe", 573215.0, 5921300.0),
    ("Priel", 573400.0, 5921140.0),
    ("Overhaken", 573420.0, 5921440.0),
    ("Hauptdeich", 573660.0, 5921330.0),
)
# Versickerung von Stauwasser aus Senken, m/h (0 = bleibt bis zur
# Ueberlaufhoehe stehen). 10 cm/h: sandiges Vorland, untere Spanne fuer Sand,
# da das Grundwasser hoch steht; angenommen, keine Messung.
INUNDATION_DRAIN_M_PER_H = 0.10
# Fliessgeschwindigkeit beim flachen Ueberstroemen von Wiese/Parzellen (Manning:
# h 0,3 m, n 0,05, Gefaelle 1 promille -> ~0,3 m/s). Verzoegerung je Zelle =
# Fliessweg vom Strom / v (inundation.travel_distance).
INUNDATION_FLOW_M_S = 0.3
# Luftbild (DOP, belaubt) fuer den Satelliten-Stil der Web-Karte: LGV-WMS
# Zeitreihe, Jahr per TIME. 2022 stammt von Pleiades (geschlossene Lizenz) ->
# nur LGV-Befliegungen verwenden. Datenlizenz Deutschland - Namensnennung 2.0.
DOP_WMS_URL = "https://geodienste.hamburg.de/wms_dop_zeitreihe_belaubt"
DOP_WMS_LAYER = "dop_zeitreihe_belaubt"
DOP_YEAR = 2024
# 3D-Gebaeudemodell LoD2-DE Hamburg 2026 (CityGML-Kacheln 1x1 km, 630 MB ZIP),
# fuer Grundrisse, Bodenhoehen und (wo vorhanden) Hausnummern der Gebaeude.
LOD2_URL = (
    "https://www.daten-hamburg.de/opendata/3d_stadtmodell_lod2/"
    "LoD2-DE_HH_2026-04-28.zip"
)
