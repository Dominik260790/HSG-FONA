from datetime import date

CLUB_ID = "handball4all.schleswig-holstein.6251"
CLUB_NAME = "HSG Fockbek/Nübbel/Alt Duvenstedt"
TIMEZONE = "Europe/Berlin"

# Saisonzeitraum anpassen, wenn die neue Saison beginnt.
DATE_FROM = date(2025, 7, 1)
DATE_TO = date(2026, 6, 30)

# Hallennummern aus handball.net.
HALLS = {
    "140702": {
        "name": "Sporthalle Alt Duvenstedt",
        "slug": "alt-duvenstedt",
        "color": "#2563eb",
    },
    "140704": {
        "name": "BSH Fockbek",
        "slug": "BSH",
        "color": "#16a34a",
    },
    "140717": {
        "name": "Sporthalle Nuebbel",
        "slug": "Nuebbel",
        "color": "#dc2626",
    },
     "140703": {
        "name": "Realschule Fockbek",
        "slug": "RSH",
         "color": "#9333ea",
    },
        
    # Beispiele ergänzen:
    # "140704": {"name": "Sporthalle Fockbek", "slug": "fockbek", "color": "#16a34a"},
    # "140705": {"name": "Sporthalle Nübbel", "slug": "nuebbel", "color": "#dc2626"},
}

DEFAULT_GAME_DURATION_MINUTES = 90
TRAINING_CSV = "data/trainings.csv"
