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

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

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

try:
    from config import WEEKEND_XLSX, WEEKEND_HALL_MAP
except ImportError:
    WEEKEND_XLSX = ""
    WEEKEND_HALL_MAP = {}


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
    "januar": 1,
    "jan": 1,
    "februar": 2,
    "feb": 2,
    "maerz": 3,
    "märz": 3,
    "mrz": 3,
    "april": 4,
    "apr": 4,
    "mai": 5,
    "juni": 6,
    "jun": 6,
    "juli": 7,
    "jul": 7,
    "august": 8,
    "aug": 8,
    "september": 9,
    "sep": 9,
    "oktober": 10,
    "okt": 10,
    "november": 11,
    "nov": 11,
    "dezember": 12,
    "dez": 12,
}

WEEKEND_DEFAULT_START = time(8, 0)
WEEKEND_DEFAULT_END = time(22, 0)
WEEKEND_DEFAULT_DURATION_MINUTES = 90


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


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", text or "").strip()


def parse_time(value: str) -> time:
    value = value.strip()
    h, m = value.split(":")
    return time(int(h), int(m))


def parse_excel_time(value) -> time | None:
    if value is None:
        return None

    if isinstance(value, time):
        return value.replace(tzinfo=None)

    if isinstance(value, datetime):
        return value.time().replace(tzinfo=None)

    if isinstance(value, (int, float)):
        # Excel stores times as fractions of a day.
        if 0 <= value < 1:
            total_minutes = round(value * 24 * 60)
            hh = total_minutes // 60
            mm = total_minutes % 60
            return time(hh, mm)

    if isinstance(value, str):
        value = clean_text(value)
        match = re.match(r"^(\d{1,2})[:.](\d{2})$", value)
        if match:
            hh = int(match.group(1))
            mm = int(match.group(2))
            return time(hh, mm)

    return None


def is_meaningful_cell(value) -> bool:
    if value is None:
        return False

    if isinstance(value, str):
        return clean_text(value) != ""

    return True


def cell_text(value) -> str:
    if value is None:
        return ""

    if isinstance(value, datetime):
        return value.date().isoformat()

    if isinstance(value, time):
        return value.strftime("%H:%M")

    return clean_text(str(value))


def to_iso(dt: datetime) -> str:
    return dt.isoformat()


def safe_id(value: str) -> str:
    value = value.lower().strip()
    value = (
        value.replace("ä", "ae")
        .replace("ö", "oe")
        .replace("ü", "ue")
        .replace("ß", "ss")
    )
    value = re.sub(r"[^a-z0-9]+", "-", value)
    value = value.strip("-")
    return value or "event"


def get_row_value(row: dict, *names: str, default: str = "") -> str:
    for name in names:
        if name in row and row[name] is not None and str(row[name]).strip() != "":
            return str(row[name]).strip()
    return default


def parse_game_start(block: str) -> datetime | None:
    text = clean_text(block)
    text = re.split(r"letztes\s+Update", text, flags=re.I)[0]

    if not re.search(r"Spielbeginn", text, flags=re.I):
        return None

    match = re.search(
        r"Spielbeginn\s+"
        r"(?:Montag|Dienstag|Mittwoch|Donnerstag|Freitag|Samstag|Sonntag|Mo\.?|Di\.?|Mi\.?|Do\.?|Fr\.?|Sa\.?|So\.?)?"
        r"\s*,?\s*"
        r"(\d{1,2})\.(\d{1,2})\.(\d{4})"
        r"\s*[-–]?\s*"
        r"(\d{1,2}):(\d{2})",
        text,
        flags=re.I,
    )
    if match:
        d, m, y, hh, mm = map(int, match.groups())
        return datetime(y, m, d, hh, mm, tzinfo=BERLIN)

    match = re.search(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4}).{0,120}?(\d{1,2}):(\d{2})",
        text,
        flags=re.I,
    )
    if match:
        d, m, y, hh, mm = map(int, match.groups())
        return datetime(y, m, d, hh, mm, tzinfo=BERLIN)

    match = re.search(
        r"(\d{1,2})\.\s*([A-Za-zäÄöÖüÜ]+)\s+(\d{4}).{0,120}?(\d{1,2}):(\d{2})",
        text,
        flags=re.I,
    )
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


def extract_game_number(block: str, hall_id: str, start: datetime) -> str:
    match = re.search(r"Spielnummer\s*([0-9]+)", block, flags=re.I)
    if match:
        return match.group(1)

    return f"{hall_id}-{start:%Y%m%d%H%M}"


def strip_schedule_metadata(text: str) -> str:
    text = clean_text(text)

    text = re.split(
        r"Spielbeginn|Spielnummer|Kalender abonnieren|letztes\s+Update|Halle",
        text,
        flags=re.I,
    )[0]

    text = re.sub(
        r"\b(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?,?\s*\d{1,2}\.\d{1,2}\.?",
        " ",
        text,
        flags=re.I,
    )
    text = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", " ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)
    text = re.sub(r"\bUhr\b", " ", text, flags=re.I)

    return clean_text(text)


def clean_opponent(opponent: str) -> str:
    opponent = clean_text(opponent)

    opponent = re.split(
        r"Spielbeginn|Spielnummer|Kalender abonnieren|letztes\s+Update|Halle",
        opponent,
        flags=re.I,
    )[0]

    opponent = re.sub(r"\bUhr\b", " ", opponent, flags=re.I)
    opponent = re.sub(r"\bSpiel\b.*$", " ", opponent, flags=re.I)
    opponent = re.sub(r"\bKalender\b.*$", " ", opponent, flags=re.I)
    opponent = clean_text(opponent)

    return opponent[:80]


def extract_club_team_number_and_opponent(block: str) -> tuple[str, str]:
    text = strip_schedule_metadata(block)
    club_match = re.search(re.escape(CLUB_NAME), text, flags=re.I)

    if not club_match:
        return "", ""

    after_club = text[club_match.end():].strip()
    team_number = ""

    match = re.match(r"^(\d+)\s+(\d{1,3})\s*:\s*(\d{1,3})\s+(.+)$", after_club)
    if match:
        team_number = match.group(1)
        opponent = match.group(4)
        return team_number, clean_opponent(opponent)

    match = re.match(r"^(\d{1,3})\s*:\s*(\d{1,3})\s+(.+)$", after_club)
    if match:
        opponent = match.group(3)
        return team_number, clean_opponent(opponent)

    match = re.match(r"^(\d+)\s+(.+)$", after_club)
    if match:
        possible_number = match.group(1)
        rest = match.group(2).strip()

        if possible_number in {"2", "3", "4", "5"}:
            team_number = possible_number
            return team_number, clean_opponent(rest)

    return team_number, clean_opponent(after_club)


def extract_team_class(block: str, team_number: str) -> str:
    text = strip_schedule_metadata(block)

    club_match = re.search(re.escape(CLUB_NAME), text, flags=re.I)

    if club_match:
        prefix = text[:club_match.start()]
    else:
        prefix = text

    prefix = clean_text(prefix)
    lower = prefix.lower()

    def with_number(label: str) -> str:
        if team_number:
            return f"{label} {team_number}"
        return label

    code_match = re.search(r"\b([wm]J?[A-E](?:-[A-Za-z0-9]+)*)\b", prefix, flags=re.I)
    if code_match:
        team_class = code_match.group(1)

        m = re.match(r"([wm])J?([A-E])(.*)", team_class, flags=re.I)
        if m:
            gender = m.group(1).lower()
            age = m.group(2).upper()
            rest = m.group(3)
            team_class = f"{gender}J{age}{rest}"

        return with_number(team_class)

    youth_patterns = [
        (r"weibliche\s+jugend\s+a", "wJA"),
        (r"weibliche\s+jugend\s+b", "wJB"),
        (r"weibliche\s+jugend\s+c", "wJC"),
        (r"weibliche\s+jugend\s+d", "wJD"),
        (r"weibliche\s+jugend\s+e", "wJE"),
        (r"männliche\s+jugend\s+a", "mJA"),
        (r"maennliche\s+jugend\s+a", "mJA"),
        (r"männliche\s+jugend\s+b", "mJB"),
        (r"maennliche\s+jugend\s+b", "mJB"),
        (r"männliche\s+jugend\s+c", "mJC"),
        (r"maennliche\s+jugend\s+c", "mJC"),
        (r"männliche\s+jugend\s+d", "mJD"),
        (r"maennliche\s+jugend\s+d", "mJD"),
        (r"männliche\s+jugend\s+e", "mJE"),
        (r"maennliche\s+jugend\s+e", "mJE"),
        (r"weibliche\s+a-jugend", "wJA"),
        (r"weibliche\s+b-jugend", "wJB"),
        (r"weibliche\s+c-jugend", "wJC"),
        (r"weibliche\s+d-jugend", "wJD"),
        (r"weibliche\s+e-jugend", "wJE"),
        (r"männliche\s+a-jugend", "mJA"),
        (r"maennliche\s+a-jugend", "mJA"),
        (r"männliche\s+b-jugend", "mJB"),
        (r"maennliche\s+b-jugend", "mJB"),
        (r"männliche\s+c-jugend", "mJC"),
        (r"maennliche\s+c-jugend", "mJC"),
        (r"männliche\s+d-jugend", "mJD"),
        (r"maennliche\s+d-jugend", "mJD"),
        (r"männliche\s+e-jugend", "mJE"),
        (r"maennliche\s+e-jugend", "mJE"),
        (r"gemischt\s+f-jugend", "F-Jugend"),
        (r"f-jugend", "F-Jugend"),
    ]

    for pattern, label in youth_patterns:
        if re.search(pattern, lower):
            return with_number(label)

    if "frauen" in lower or "damen" in lower:
        number = team_number or "1"
        return f"{number}. Frauen"

    if "männer" in lower or "maenner" in lower or "herren" in lower:
        number = team_number or "1"
        return f"{number}. Männer"

    if "minis" in lower or "mini" in lower:
        return with_number("Minis")

    if "maxis" in lower or "maxi" in lower:
        return with_number("Maxis")

    fallback = prefix

    fallback = re.sub(r"\bRegion\s+(Jugend|Erwachsene|Mitte|Nord|Süd|Sued)\b", " ", fallback, flags=re.I)
    fallback = re.sub(r"\bSchleswig-Holstein\b", " ", fallback, flags=re.I)
    fallback = re.sub(r"\bKreisliga\b|\bKreisoberliga\b|\bOberliga\b|\bRegionsliga\b|\bPokal\b", " ", fallback, flags=re.I)
    fallback = re.sub(r"\bHinrunde\b|\bRückrunde\b|\bRueckrunde\b|\bStaffel\b", " ", fallback, flags=re.I)
    fallback = re.sub(r"\bRD\b|\bNMS\b|\bSE\b", " ", fallback, flags=re.I)
    fallback = re.sub(r"\s*-\s*", " ", fallback)
    fallback = clean_text(fallback)

    if fallback:
        return with_number(fallback[:30])

    if team_number:
        return f"{team_number}. Mannschaft"

    return "Mannschaft"


def extract_game_title(block: str, start: datetime) -> str:
    team_number, opponent = extract_club_team_number_and_opponent(block)
    team_class = extract_team_class(block, team_number)

    parts = [team_class]

    if opponent:
        parts.append(opponent)

    return " · ".join(parts)


def fetch_handballnet_games() -> list[CalendarEvent]:
    base_url = (
        f"https://www.handball.net/vereine/{CLUB_ID}/spielplan"
        f"?dateFrom={DATE_FROM.isoformat()}&dateTo={DATE_TO.isoformat()}"
    )

    headers = {
        "User-Agent": "Mozilla/5.0 hallenkalender-import/1.0 (+https://github.com/)",
        "Accept-Language": "de-DE,de;q=0.9,en;q=0.8",
    }

    events: list[CalendarEvent] = []
    seen: set[str] = set()

    max_pages = 20
    pages_without_new_events = 0

    for page in range(1, max_pages + 1):
        if page == 1:
            url = base_url
        else:
            url = f"{base_url}&page={page}"

        print(f"Fetching handball.net page {page}: {url}")

        response = requests.get(url, headers=headers, timeout=30)
        response.raise_for_status()

        soup = BeautifulSoup(response.text, "html.parser")

        text_blocks: list[str] = []

        for tag in soup.find_all(["article", "section", "li", "tr", "div"]):
            txt = clean_text(tag.get_text(" "))

            if len(txt) < 80 or len(txt) > 2500:
                continue

            if "Spielbeginn" not in txt:
                continue

            if "Spielnummer" not in txt:
                continue

            if not any(hall_id in txt for hall_id in HALLS):
                continue

            text_blocks.append(txt)

        before_count = len(events)

        for block in text_blocks:
            block_without_update = re.split(r"letztes\s+Update", block, flags=re.I)[0]

            for hall_id, hall in HALLS.items():
                if hall_id not in block_without_update:
                    continue

                start = parse_game_start(block_without_update)

                if not start:
                    continue

                end = start + timedelta(minutes=DEFAULT_GAME_DURATION_MINUTES)

                game_no = extract_game_number(block_without_update, hall_id, start)
                event_id = f"handballnet-{game_no}"

                if event_id in seen:
                    continue

                seen.add(event_id)

                title = extract_game_title(block_without_update, start)

                events.append(
                    CalendarEvent(
                        id=event_id,
                        title=title,
                        start=to_iso(start),
                        end=to_iso(end),
                        hall_id=hall_id,
                        hall=hall["name"],
                        type="game",
                        source="handball.net",
                        location=hall["name"],
                        description=(
                            f"Quelle: handball.net | {CLUB_NAME} | "
                            f"Hallennummer {hall_id} | Spielnummer {game_no}"
                        ),
                        url=url,
                        color=hall.get("color", ""),
                    )
                )

        new_events = len(events) - before_count
        print(f"handball.net page {page}: {new_events} new hall games")

        if new_events == 0:
            pages_without_new_events += 1
        else:
            pages_without_new_events = 0

        if pages_without_new_events >= 4:
            print("Stopping handball.net pagination after 4 pages without new hall games.")
            break

    return sorted(events, key=lambda e: e.start)


def title_for_training_event(event_type: str, team: str) -> str:
    event_type = (event_type or "training").strip().lower()
    team = clean_text(team)

    if event_type == "blocked":
        if team and team.lower() != "belegt":
            return f"Belegt: {team}"
        return "Belegt"

    if event_type == "football":
        return "Fußballerzeit"

    if event_type == "optional":
        if team:
            return f"Optional: {team}"
        return "Optional"

    if event_type == "game":
        return team or "Spiel"

    if team:
        return f"Training {team}"

    return "Training"


def load_training_events() -> list[CalendarEvent]:
    path = ROOT / TRAINING_CSV
    if not path.exists():
        print(f"WARNING: training CSV not found: {path}")
        return []

    events: list[CalendarEvent] = []

    with path.open("r", encoding="utf-8-sig", newline="") as f:
        reader = csv.DictReader(f)

        for row in reader:
            hall_id = get_row_value(row, "hall_id")

            if hall_id not in HALLS:
                print(f"WARNING: unknown hall_id in training CSV skipped: {hall_id}")
                continue

            weekday_key = get_row_value(row, "weekday").upper()

            if weekday_key not in WEEKDAYS:
                print(f"WARNING: unknown weekday skipped: {weekday_key}")
                continue

            weekday = WEEKDAYS[weekday_key]

            start_date_raw = get_row_value(row, "date_from", "valid_from")
            end_date_raw = get_row_value(row, "date_to", "valid_to")

            if not start_date_raw or not end_date_raw:
                print(f"WARNING: missing date_from/date_to skipped: {row}")
                continue

            start_date = date.fromisoformat(start_date_raw)
            end_date = date.fromisoformat(end_date_raw)

            first = start_date + timedelta(days=(weekday - start_date.weekday()) % 7)

            start_t = parse_time(get_row_value(row, "start_time"))
            end_t = parse_time(get_row_value(row, "end_time"))

            event_type = get_row_value(row, "type", default="training") or "training"
            team = get_row_value(row, "team")
            notes = get_row_value(row, "notes")
            hall = HALLS[hall_id]

            for day_dt in rrule(
                WEEKLY,
                dtstart=datetime.combine(first, time(0, 0)),
                until=datetime.combine(end_date, time(23, 59)),
            ):
                start = datetime.combine(day_dt.date(), start_t, tzinfo=BERLIN)
                end = datetime.combine(day_dt.date(), end_t, tzinfo=BERLIN)

                event_id = f"{event_type}-{hall_id}-{safe_id(team)}-{start:%Y%m%d%H%M}"

                events.append(
                    CalendarEvent(
                        id=event_id,
                        title=title_for_training_event(event_type, team),
                        start=to_iso(start),
                        end=to_iso(end),
                        hall_id=hall_id,
                        hall=hall["name"],
                        type=event_type,
                        source="trainings.csv",
                        location=hall["name"],
                        description=notes,
                        color=hall.get("color", ""),
                    )
                )

    return events


def find_weekend_hall_columns(ws) -> list[dict]:
    hall_columns: list[dict] = []

    for row in range(1, min(ws.max_row, 5) + 1):
        for col in range(1, ws.max_column + 1):
            value = cell_text(ws.cell(row, col).value)

            if not value:
                continue

            for excel_hall_name, hall_id in WEEKEND_HALL_MAP.items():
                if clean_text(value).lower() == clean_text(excel_hall_name).lower():
                    if hall_id not in HALLS:
                        print(f"WARNING: weekend hall maps to unknown hall_id skipped: {excel_hall_name} -> {hall_id}")
                        continue

                    # In the template:
                    # BSH text col = 4, time col = 2
                    # Duvenstedt text col = 7, time col = 5
                    # Nübbel text col = 10, time col = 8
                    # Bergschule text col = 13, time col = 11
                    hall_columns.append(
                        {
                            "excel_name": excel_hall_name,
                            "hall_id": hall_id,
                            "text_col": col,
                            "time_col": max(1, col - 2),
                        }
                    )

    unique = {}
    for item in hall_columns:
        unique[(item["hall_id"], item["text_col"])] = item

    return list(unique.values())


def is_weekday_label(value) -> bool:
    if not isinstance(value, str):
        return False

    value = clean_text(value).lower()

    return value in {
        "montag",
        "dienstag",
        "mittwoch",
        "donnerstag",
        "freitag",
        "samstag",
        "sonntag",
    }


def find_weekend_date_sections(ws) -> list[dict]:
    date_rows: list[tuple[int, date]] = []

    for row in range(1, ws.max_row + 1):
        value = ws.cell(row, 1).value

        if isinstance(value, datetime):
            date_rows.append((row, value.date()))

        elif isinstance(value, date):
            date_rows.append((row, value))

    sections: list[dict] = []

    for index, (date_row, day_date) in enumerate(date_rows):
        if date_row > 1 and is_weekday_label(ws.cell(date_row - 1, 1).value):
            start_row = date_row - 1
        else:
            start_row = date_row

        if index + 1 < len(date_rows):
            next_date_row = date_rows[index + 1][0]
            if next_date_row > 1 and is_weekday_label(ws.cell(next_date_row - 1, 1).value):
                end_row = next_date_row - 2
            else:
                end_row = next_date_row - 1
        else:
            end_row = ws.max_row

        sections.append(
            {
                "date": day_date,
                "start_row": start_row,
                "date_row": date_row,
                "end_row": end_row,
            }
        )

    return sections


def collect_weekend_text_lines(ws, rows: list[int], time_col: int, text_col: int) -> list[str]:
    lines: list[str] = []

    for row in rows:
        values = [
            ws.cell(row, text_col).value,
        ]

        # Notes sometimes appear inside the time column, e.g. "Feiertag Vergabe nur ...".
        time_value = ws.cell(row, time_col).value
        if parse_excel_time(time_value) is None:
            values.append(time_value)

        for value in values:
            if not is_meaningful_cell(value):
                continue

            if isinstance(value, (datetime, date, time)):
                continue

            text = cell_text(value)

            if not text:
                continue

            if is_weekday_label(text):
                continue

            if text not in lines:
                lines.append(text)

    return lines


def is_full_day_weekend_event(title: str) -> bool:
    lower = title.lower()

    keywords = [
        "ferien",
        "gesperrt",
        "feiertag",
        "osterwochenende",
        "pfingsten",
        "nutzung nur auf antrag",
        "vergab",
        "genehmigung",
        "zeiten folgen",
    ]

    return any(keyword in lower for keyword in keywords)


def make_weekend_title(lines: list[str]) -> str:
    title = " / ".join(clean_text(line) for line in lines if clean_text(line))
    title = clean_text(title)

    if not title:
        return "Wochenendbelegung"

    return title[:160]


def load_weekend_excel_events() -> list[CalendarEvent]:
    if not WEEKEND_XLSX:
        print("weekend excel: disabled, WEEKEND_XLSX not configured")
        return []

    if not WEEKEND_HALL_MAP:
        print("weekend excel: disabled, WEEKEND_HALL_MAP not configured")
        return []

    if load_workbook is None:
        print("WARNING: openpyxl not installed, weekend excel skipped")
        return []

    path = ROOT / WEEKEND_XLSX

    if not path.exists():
        print(f"weekend excel: file not found, skipped: {path}")
        return []

    workbook = load_workbook(path, data_only=True)
    events: list[CalendarEvent] = []
    seen: set[str] = set()

    for ws in workbook.worksheets:
        hall_columns = find_weekend_hall_columns(ws)

        if not hall_columns:
            continue

        date_sections = find_weekend_date_sections(ws)

        for section in date_sections:
            day_date = section["date"]
            start_row = section["start_row"]
            end_row = section["end_row"]

            for hall_config in hall_columns:
                hall_id = hall_config["hall_id"]
                hall = HALLS[hall_id]
                time_col = hall_config["time_col"]
                text_col = hall_config["text_col"]

                rows = list(range(start_row, end_row + 1))

                time_rows = []
                for row in rows:
                    parsed_time = parse_excel_time(ws.cell(row, time_col).value)
                    if parsed_time is not None:
                        time_rows.append((row, parsed_time))

                if time_rows:
                    for idx, (time_row, start_t) in enumerate(time_rows):
                        if idx == 0:
                            chunk_start = start_row
                        else:
                            chunk_start = time_row

                        if idx + 1 < len(time_rows):
                            chunk_end = time_rows[idx + 1][0] - 1
                            end_t = time_rows[idx + 1][1]
                        else:
                            chunk_end = end_row
                            end_dt_tmp = datetime.combine(day_date, start_t) + timedelta(minutes=WEEKEND_DEFAULT_DURATION_MINUTES)
                            end_t = end_dt_tmp.time()

                        chunk_rows = list(range(chunk_start, chunk_end + 1))
                        lines = collect_weekend_text_lines(ws, chunk_rows, time_col, text_col)

                        if not lines:
                            continue

                        title = make_weekend_title(lines)

                        start = datetime.combine(day_date, start_t, tzinfo=BERLIN)
                        end = datetime.combine(day_date, end_t, tzinfo=BERLIN)

                        if end <= start:
                            end = start + timedelta(minutes=WEEKEND_DEFAULT_DURATION_MINUTES)

                        event_id = f"weekend-{hall_id}-{safe_id(ws.title)}-{day_date.isoformat()}-{start:%H%M}-{safe_id(title)}"

                        if event_id in seen:
                            continue

                        seen.add(event_id)

                        events.append(
                            CalendarEvent(
                                id=event_id,
                                title=title,
                                start=to_iso(start),
                                end=to_iso(end),
                                hall_id=hall_id,
                                hall=hall["name"],
                                type="weekend",
                                source="weekend_belegung.xlsx",
                                location=hall["name"],
                                description=(
                                    f"Quelle: {WEEKEND_XLSX} | Blatt: {ws.title} | "
                                    f"Excel-Halle: {hall_config['excel_name']}"
                                ),
                                color=hall.get("color", ""),
                            )
                        )

                else:
                    lines = collect_weekend_text_lines(ws, rows, time_col, text_col)

                    if not lines:
                        continue

                    title = make_weekend_title(lines)

                    if is_full_day_weekend_event(title):
                        start_t = WEEKEND_DEFAULT_START
                        end_t = WEEKEND_DEFAULT_END
                    else:
                        start_t = WEEKEND_DEFAULT_START
                        end_t = (
                            datetime.combine(day_date, start_t) + timedelta(minutes=WEEKEND_DEFAULT_DURATION_MINUTES)
                        ).time()

                    start = datetime.combine(day_date, start_t, tzinfo=BERLIN)
                    end = datetime.combine(day_date, end_t, tzinfo=BERLIN)

                    event_id = f"weekend-{hall_id}-{safe_id(ws.title)}-{day_date.isoformat()}-{safe_id(title)}"

                    if event_id in seen:
                        continue

                    seen.add(event_id)

                    events.append(
                        CalendarEvent(
                            id=event_id,
                            title=title,
                            start=to_iso(start),
                            end=to_iso(end),
                            hall_id=hall_id,
                            hall=hall["name"],
                            type="weekend",
                            source="weekend_belegung.xlsx",
                            location=hall["name"],
                            description=(
                                f"Quelle: {WEEKEND_XLSX} | Blatt: {ws.title} | "
                                f"Excel-Halle: {hall_config['excel_name']} | "
                                f"keine konkrete Uhrzeit in Excel gefunden"
                            ),
                            color=hall.get("color", ""),
                        )
                    )

    print(f"weekend excel sheets parsed: {len(workbook.worksheets)}")
    return sorted(events, key=lambda e: e.start)


def ics_escape(value: str) -> str:
    value = html.unescape(str(value or ""))
    return (
        value.replace("\\", "\\\\")
        .replace(";", "\\;")
        .replace(",", "\\,")
        .replace("\n", "\\n")
    )


def ics_dt(value: str) -> str:
    dt = datetime.fromisoformat(value)
    return dt.strftime("%Y%m%dT%H%M%S")


def write_ics(filename: str, calendar_name: str, events: Iterable[CalendarEvent]) -> None:
    now = datetime.utcnow().strftime("%Y%m%dT%H%M%SZ")

    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HSG FONA//Hallenkalender//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{ics_escape(calendar_name)}",
        f"X-WR-TIMEZONE:{TIMEZONE}",
    ]

    for event in sorted(events, key=lambda e: e.start):
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{ics_escape(event.id)}@hallenkalender.local",
                f"DTSTAMP:{now}",
                f"DTSTART;TZID={TIMEZONE}:{ics_dt(event.start)}",
                f"DTEND;TZID={TIMEZONE}:{ics_dt(event.end)}",
                f"SUMMARY:{ics_escape(event.title)}",
                f"LOCATION:{ics_escape(event.location)}",
                f"DESCRIPTION:{ics_escape(event.description)}",
            ]
        )

        if event.url:
            lines.append(f"URL:{ics_escape(event.url)}")

        lines.append("END:VEVENT")

    lines.append("END:VCALENDAR")

    (ROOT / "calendars" / filename).write_text(
        "\r\n".join(lines) + "\r\n",
        encoding="utf-8",
    )


def main() -> None:
    ensure_dirs()

    games: list[CalendarEvent] = []

    try:
        games = fetch_handballnet_games()
        print(f"handball.net games: {len(games)}")
    except Exception as exc:
        print(f"WARNING: handball.net import failed: {exc}")

    trainings = load_training_events()
    print(f"training events: {len(trainings)}")

    weekend_events = load_weekend_excel_events()
    print(f"weekend excel events: {len(weekend_events)}")

    events = sorted(games + trainings + weekend_events, key=lambda e: e.start)

    (ROOT / "data" / "events.json").write_text(
        json.dumps([asdict(e) for e in events], ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_ics("gesamt.ics", "Hallenbelegung gesamt", events)

    for hall_id, hall in HALLS.items():
        hall_events = [event for event in events if event.hall_id == hall_id]
        write_ics(f"{hall['slug']}.ics", hall["name"], hall_events)

    print(f"written events: {len(events)}")


if __name__ == "__main__":
    main()
