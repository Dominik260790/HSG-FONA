from datetime import date

CLUB_ID = "handball4all.schleswig-holstein.6251"
CLUB_NAME = "HSG Fockbek/Nübbel/Alt Duvenstedt"
TIMEZONE = "Europe/Berlin"

# Saisonzeitraum anpassen, wenn die neue Saison beginnt.
DATE_FROM = date(2026, 4, 1)
DATE_TO = date(2027, 05, 31)

# Hallennummern aus handball.net.
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
        "name": "Sporthalle Nuebbel",
        "slug": "nuebbel",
        "color": "#dc2626",
    },
     "140703": {
        "name": "Realschule Fockbek",
        "slug": "realschule",
         "color": "#9333ea",
    },
        
    # Beispiele ergänzen:
    # "140704": {"name": "Sporthalle Fockbek", "slug": "fockbek", "color": "#16a34a"},
    # "140705": {"name": "Sporthalle Nübbel", "slug": "nuebbel", "color": "#dc2626"},
}

DEFAULT_GAME_DURATION_MINUTES = 90
TRAINING_CSV = "data/trainings.csv"
WEEKEND_XLSX = "data/weekend_belegung.xlsx"

WEEKEND_HALL_MAP = {
    "Bgm.-Schadwinkel-Halle": "140704",
    "Sporthalle Duvenstedt": "140702",
    "Sporthalle Nübbel": "140717",
    "Sporthalle Bergschule": "140703",
}
EXTRA_EVENTS_CSV_URL = "https://docs.google.com/spreadsheets/d/e/2PACX-1vQDHmRhn3c3B1ozudVJ3BL7zHvACLcVfG9pcz_s6JpQXgyxShNGSAq4xYAjrCDFoguM03-VBjaXl3gh/pub?output=csv"


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
