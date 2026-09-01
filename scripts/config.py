from datetime import date


CLUB_NAME = "HSG Fockbek/Nübbel/Alt Duvenstedt"
TIMEZONE = "Europe/Berlin"


# Zeitraum, der im Hallenkalender berücksichtigt wird.
# Bei einer neuen Saison hier entsprechend anpassen.
DATE_FROM = date(2026, 4, 1)
DATE_TO = date(2027, 5, 31)


# Unsere Hallen
HALLS = {
    "140702": {
        "name": "Sporthalle Alt Duvenstedt",
        "slug": "alt-duvenstedt",
        "color": "#2563eb",
    },

    "140704": {
        "name": "BSH Fockbek",
        "slug": "bsh",
        "color": "#16a34a",
    },

    "140717": {
        "name": "Sporthalle Nübbel",
        "slug": "nuebbel",
        "color": "#dc2626",
    },

    "140703": {
        "name": "Realschule Fockbek",
        "slug": "realschule",
        "color": "#9333ea",
    },
}


# Standarddauer eines Spiels
DEFAULT_GAME_DURATION_MINUTES = 90


# ---------------------------------------------------------
# TRAININGSPLAN
# ---------------------------------------------------------

TRAINING_CSV = "data/trainings.csv"


# ---------------------------------------------------------
# MISQUAD
# ---------------------------------------------------------

# Die jeweils aktuelle MISQUAD-Datei muss im Repository
# immer unter diesem Namen liegen:
MISQUAD_XLSX = "data/misquad.xlsx"


# Zuordnung der Hallennamen aus MISQUAD
#
# WICHTIG:
# "SPORTHALLE" bedeutet bei HSG-Heimspielen Sporthalle Nübbel.
# Der Import berücksichtigt hierfür ausschließlich Heimspiele
# der HSG.
MISQUAD_HALL_MAP = {
    "SPORTHALLE ALT DUVENSTEDT": "140702",

    "BÜRGERMEISTER-SCHADWINKEL-HALLE": "140704",

    "SPORTHALLE": "140717",
    "SPORTHALLE NÜBBEL": "140717",
    "SPORTHALLE NUEBBEL": "140717",

    # vorsorglich für zukünftige MISQUAD-Bezeichnungen
    "REALSCHULE FOCKBEK": "140703",
    "SPORTHALLE BERGSCHULE": "140703",
}


# ---------------------------------------------------------
# WOCHENENDBELEGUNG
# ---------------------------------------------------------

WEEKEND_XLSX = "data/weekend_belegung.xlsx"

WEEKEND_HALL_MAP = {
    "Bgm.-Schadwinkel-Halle": "140704",
    "Sporthalle Duvenstedt": "140702",
    "Sporthalle Nübbel": "140717",
    "Sporthalle Bergschule": "140703",
}


# ---------------------------------------------------------
# GOOGLE FORM / ZUSATZTERMINE
# ---------------------------------------------------------

EXTRA_EVENTS_CSV_URL = (
    "https://docs.google.com/spreadsheets/d/e/"
    "2PACX-1vQDHmRhn3c3B1ozudVJ3BL7zHvACLcVfG9pcz_s6JpQXgyxShNGSAq4xYAjrCDFoguM03-VBjaXl3gh/"
    "pub?output=csv"
)


EXTRA_HALL_MAP = {
    "Sporthalle Alt Duvenstedt": "140702",
    "Alt Duvenstedt": "140702",

    "BSH Fockbek": "140704",
    "Bgm.-Schadwinkel-Halle": "140704",

    "Realschule Fockbek": "140703",
    "Sporthalle Bergschule": "140703",
    "Bergschule": "140703",

    "Sporthalle Nübbel": "140717",
    "Sporthalle Nuebbel": "140717",
    "Nübbel": "140717",
    "Nuebbel": "140717",
}


EXTRA_TYPE_MAP = {
    "Zusatztermin": "event",
    "Trainingslager": "camp",
    "Turnier": "tournament",
    "Belegt": "blocked",
}
