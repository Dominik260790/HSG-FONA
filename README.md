# Kostenloser Hallenkalender: handball.net + Training + Website + iCal

Kostenfreie Startlösung für 3 Hallen:

- GitHub Pages veröffentlicht die Website
- GitHub Actions aktualisiert automatisch die Daten
- FullCalendar zeigt den Kalender im Browser
- Python erzeugt `events.json` und `.ics`-Feeds
- Trainingszeiten werden über `data/trainings.csv` gepflegt

## Enthaltene Hallen

Bitte in `scripts/config.py` anpassen:

```python
HALLS = {
    "140702": {
        "name": "Sporthalle Alt Duvenstedt",
        "slug": "alt-duvenstedt",
        "color": "#2563eb",
    },
}
```

Weitere Hallen ergänzen, z. B. Fockbek und Nübbel.

## Lokaler Test

```bash
pip install -r requirements.txt
python scripts/import_calendar.py
python -m http.server 8000
```

Dann öffnen:

```text
http://localhost:8000
```

## GitHub Pages aktivieren

1. Repository bei GitHub erstellen
2. Dateien hochladen
3. Settings -> Pages
4. Source: GitHub Actions auswählen
5. Nach dem nächsten Workflow-Lauf ist die Seite online

## Automatische Aktualisierung

Der Workflow läuft täglich um 05:15 Uhr UTC und kann manuell gestartet werden.

## iCal-Feeds

Nach dem Lauf entstehen:

```text
calendars/alt-duvenstedt.ics
calendars/gesamt.ics
```

Diese URLs können in Google Kalender, Outlook oder Apple Kalender abonniert werden.

## Hinweis zu handball.net

Das Skript ist als belastbarer Startpunkt gebaut. Falls handball.net seine HTML-Struktur ändert oder die Daten per interner API liefert, muss die Funktion `fetch_handballnet_games()` in `scripts/import_calendar.py` angepasst werden.
