"""Statische Konfiguration: Orte, Stationsnamen, Modell-Defaults."""

# Elbe-Kilometrierung (km waechst stromab)
ELBE_KM = {
    "zollenspieker": 598.3,
    "over": 605.3,  # Messpegel direkt gegenueber Overwerder
    "overwerder": 605.3,  # Zielort: Overwerder
    "bunthaus": 609.8,
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
PEGELONLINE_WEB_BASE = "https://www.pegelonline.wsv.de/gast"
PEGELONLINE_HISTORY_PARAMETER = "WASSERSTAND ROHDATEN"
PEGELONLINE_HISTORY_START = "2000-01-01"  # frueheste im Archiv verfuegbare Daten
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

# Historische Sturmflut-Scheitel am Pegel Over (cm ueber PNP), Raenge 1/3/5/10.
# Einzige Quelle fuer Plot (plot.py) und Web-Export (webexport.py); die volle
# Tabelle samt Methodik steht in docs/TOP_10_STURMFLUTEN.md.
STURMFLUT_DOC = "docs/TOP_10_STURMFLUTEN.md"
STURMFLUT_DOC_URL = (
    "https://github.com/aaronspring/wasserstandvorhersage_overwerder/"
    "blob/main/docs/TOP_10_STURMFLUTEN.md"
)
STURMFLUT_SCHEITEL_CM = {
    1: (1114, "Xaver 2013"),
    3: (1067, "Tilo 2007"),
    5: (1060, "Dez. 2023"),
    10: (1008, "Emma 2008"),
}

HTTP_TIMEOUT = 30  # Sekunden
USER_AGENT = "wasserstandvorhersage-overwerder/0.1 (github.com/aaronspring)"
