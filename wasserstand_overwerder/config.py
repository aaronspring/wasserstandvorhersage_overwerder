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

# Plausibler Wertebereich fuer Tideelbe-Wasserstaende in cm ueber PNP
# (PNP = NHN - 5,00 m): grob 100..1100 cm. Dient der Einheiten-Pruefung.
PLAUSIBLE_CM_PNP = (50.0, 1300.0)

HTTP_TIMEOUT = 30  # Sekunden
USER_AGENT = "wasserstandvorhersage-overwerder/0.1 (github.com/aaronspring)"
