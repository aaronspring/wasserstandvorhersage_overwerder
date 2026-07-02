"""Statische Konfiguration: Orte, Stationsnamen, Modell-Defaults."""

# Elbe-Kilometrierung (km waechst stromab)
ELBE_KM = {
    "zollenspieker": 598.3,
    "over": 605.3,        # Messpegel direkt gegenueber Overwerder
    "overwerder": 605.3,  # Zielort: Overwerder Bogen 79
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
