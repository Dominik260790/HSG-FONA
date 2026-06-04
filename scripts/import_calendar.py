import csv
import html
import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Iterable
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup
from dateutil.rrule import rrule, WEEKLY

from config import (
    CLUB_ID,
    CLUB_NAME,
    TIMEZONE,
    DATE_FROM,
    DATE_TO,
    HALLS,
    DEFAULT_GAME_DURATION_MINUTES,
    TRAINING_CSV,
)

ROOT = Path(__file__).resolve().parents[1]
BERLIN = ZoneInfo(TIMEZONE)

WEEKDAYS = {
    "MO": 0,
    "DI": 1,
    "MI": 2,
    "DO": 3,
    "FR": 4,
    "SA": 5,
    "SO": 6,
    "TU": 1,
    "WE": 2,
    "TH": 3,
    "SU": 6,
}

GERMAN_MONTHS = {
    "januar": 1, "jan": 1,
    "februar": 2, "feb": 2,
    "märz": 3, "maerz": 3, "mrz": 3,
    "april": 4, "apr": 4,
    "mai": 5,
    "juni": 6, "jun": 6,
    "juli": 7, "jul": 7,
    "august": 8, "aug": 8,
    "september": 9, "sep": 9,
    "oktober": 10, "okt": 10,
    "november": 11, "nov": 11,
    "dezember": 12, "dez": 12,
}

@dataclass
class CalendarEvent:
    id: str
    title: str
    start: str
    end: str
    hall_id: str
    hall: str
    type: str
    source: str
    location: str = ""
    description: str = ""
    url: str = ""
    color: str = ""


def ensure_dirs() -> None:
    (ROOT / "data").mkdir(exist_ok=True)
    (ROOT / "calendars").mkdir(exist_ok=True)


def parse_time(value: str) -> time:
    h, m = value.strip().split(":")
    return time(int(h), int(m))


def to_iso(dt: datetime) -> str:
    return dt.isoformat()


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_german_datetime(text: str) -> datetime | None:
    """Finds dates like 25.04.2026 13:00 or 25. April 2026 - 13:00 Uhr."""
    text = clean_text(text).replace("Uhr", "")

    match = re.search(r"(\d{1,2})\.(\d{1,2})\.(\d{4}).{0,20}?(\d{1,2}):(\d{2})", text)
    if match:
        d, m, y, hh, mm = map(int, match.groups())
        return datetime(y, m, d, hh, mm, tzinfo=BERLIN)

    match = re.search(r"(\d{1,2})\.\s*([A-Za-zäÄöÖüÜ]+)\s+(\d{4}).{0,20}?(\d{1,2}):(\d{2})", text)
    if match:
        d = int(match.group(1))
        month_name = match.group(2).lower().replace("ä", "ae")
        m = GERMAN_MONTHS.get(month_name)
        if not m:
            return None
        y = int(match.group(3))
        hh = int(match.group(4))
        mm = int(match.group(5))
        return datetime(y, m, d, hh, mm, tzinfo=BERLIN)

    return None


def fetch_handballnet_games() -> list[CalendarEvent]:
    """Fetch club schedule from handball.net and parse games.

    This parser intentionally works conservatively:
    - It requests the public club schedule for the configured season.
    - It searches text blocks containing a configured hall number.
    - It extracts date/time and a plausible title.

    If handball.net exposes a stable JSON endpoint in your browser network tab,
    replacing this function with direct JSON parsing is recommended.
    """
    url = (
        f"https://www.handball.net/vereine/{CLUB_ID}/spielplan"
        f"?dateFrom={DATE_FROM.isoformat()}&dateTo={DATE_TO.isoformat()}"
    )
    headers = {
        "User-Agent": "Mozilla/5.0 hallenkalender-import/1.0 (+https://github.com/)",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }
    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")
    text_blocks = []

    # Prefer medium-sized blocks; whole page text is too noisy, tiny nodes miss context.
    for tag in soup.find_all(["article", "section", "li", "tr", "div"]):
        txt = clean_text(tag.get_text(" "))
        if 40 <= len(txt) <= 1500 and any(hall_id in txt for hall_id in HALLS):
            text_blocks.append(txt)

    events: list[CalendarEvent] = []
    seen: set[str] = set()

    for block in text_blocks:
        for hall_id, hall in HALLS.items():
            if hall_id not in block:
                continue

            start = parse_german_datetime(block)
            if not start:
                continue
            end = start + timedelta(minutes=DEFAULT_GAME_DURATION_MINUTES)

            game_no_match = re.search(r"Spielnummer\s*([0-9]+)", block, flags=re.I)
            game_no = game_no_match.group(1) if game_no_match else f"{hall_id}-{start:%Y%m%d%H%M}"
            event_id = f"handballnet-{game_no}"
            if event_id in seen:
                continue
            seen.add(event_id)

            title = extract_title(block)
            events.append(CalendarEvent(
                id=event_id,
                title=title,
                start=to_iso(start),
                end=to_iso(end),
                hall_id=hall_id,
                hall=hall["name"],
                type="game",
                source="handball.net",
                location=hall["name"],
                description=f"Quelle: handball.net | {CLUB_NAME} | Hallennummer {hall_id}",
                url=url,
                color=hall.get("color", ""),
            ))

    return sorted(events, key=lambda e: e.start)


def extract_title(block: str) -> str:
    # Try to remove common noise. This can be refined after seeing real HTML blocks.
    cleaned = re.sub(r"Spielnummer\s*[0-9]+", "", block, flags=re.I)
    cleaned = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", "", cleaned)
    cleaned = re.sub(r"\b\d{1,2}:\d{2}\b", "", cleaned)
    cleaned = re.sub(r"Sporthalle[^()]+\([0-9]+\)", "", cleaned)
    cleaned = clean_text(cleaned)
    return cleaned[:120] if cleaned else "Handballspiel"


def load_training_events() -> list[CalendarEvent]:
    path = ROOT / TRAINING_CSV
    if not path.exists():
        return []

    events: list[CalendarEvent] = []
    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)
        for row in reader:
            hall_id = row["hall_id"].strip()
            if hall_id not in HALLS:
                continue
            weekday = WEEKDAYS[row["weekday"].strip().upper()]
            start_date = date.fromisoformat(row["date_from"].strip())
            end_date = date.fromisoformat(row["date_to"].strip())
            first = start_date + timedelta(days=(weekday - start_date.weekday()) % 7)
            start_t = parse_time(row["start_time"])
            end_t = parse_time(row["end_time"])

            for day_dt in rrule(WEEKLY, dtstart=datetime.combine(first, time(0, 0)), until=datetime.combine(end_date, time(23, 59))):
                start = datetime.combine(day_dt.date(), start_t, tzinfo=BERLIN)
                end = datetime.combine(day_dt.date(), end_t, tzinfo=BERLIN)
                team = row["team"].strip()
                eid = f"training-{hall_id}-{team}-{start:%Y%m%d%H%M}".lower().replace(" ", "-")
                hall = HALLS[hall_id]
                events.append(CalendarEvent(
                    id=eid,
                    title=f"Training {team}",
                    start=to_iso(start),
                    end=to_iso(end),
                    hall_id=hall_id,
                    hall=hall["name"],
                    type=row.get("type", "training").strip() or "training",
                    source="trainings.csv",
                    location=hall["name"],
                    description=row.get("notes", ""),
                    color=hall.get("color", ""),
                ))
    return events


def ics_escape(value: str) -> str:
    value = html.unescape(str(value or ""))
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def ics_dt(value: str) -> str:
    dt = datetime.fromisoformat(value)
    return dt.strftime("%Y%m%dT%H%M%S")


def write_ics(filename: str, calendar_name: str, events: Iterable[CalendarEvent]) -> None:
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HSG FNA//Hallenkalender//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
        f"X-WR-TIMEZONE:{TIMEZONE}",
    ]
    for event in sorted(events, key=lambda e: e.start):
        lines.extend([
            "BEGIN:VEVENT",
            f"UID:{event.id}@hallenkalender.local",
            f"DTSTAMP:{now}",
            f"DTSTART;TZID={TIMEZONE}:{ics_dt(event.start)}",
            f"DTEND;TZID={TIMEZONE}:{ics_dt(event.end)}",
            f"SUMMARY:{ics_escape(event.title)}",
            f"LOCATION:{ics_escape(event.location)}",
            f"DESCRIPTION:{ics_escape(event.description)}",
        ])
        if event.url:
            lines.append(f"URL:{ics_escape(event.url)}")
        lines.append("END:VEVENT")
    lines.append("END:VCALENDAR")
    (ROOT / "calendars" / filename).write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def main() -> None:
    ensure_dirs()

    games = []
    try:
        games = fetch_handballnet_games()
        print(f"handball.net games: {len(games)}")
    except Exception as exc:
        print(f"WARNING: handball.net import failed: {exc}")

    trainings = load_training_events()
    print(f"training events: {len(trainings)}")

    events = sorted(games + trainings, key=lambda e: e.start)

    (ROOT / "data" / "events.json").write_text(
        json.dumps([asdict(e) for e in events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_ics("gesamt.ics", "Hallenbelegung gesamt", events)
    for hall_id, hall in HALLS.items():
        hall_events = [e for e in events if e.hall_id == hall_id]
        write_ics(f"{hall['slug']}.ics", hall["name"], hall_events)

    print(f"written events: {len(events)}")


if __name__ == "__main__":
    main()
