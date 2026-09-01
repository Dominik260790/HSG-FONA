import csv
import hashlib
import io
import json
import re
import zipfile
import xml.etree.ElementTree as ET

from collections import Counter
from dataclasses import asdict, dataclass
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from typing import Optional

import requests

try:
    from openpyxl import load_workbook
except ImportError:
    load_workbook = None

from config import (
    CLUB_NAME,
    TIMEZONE,
    DATE_FROM,
    DATE_TO,
    HALLS,
    DEFAULT_GAME_DURATION_MINUTES,
    TRAINING_CSV,
    MISQUAD_XLSX,
    MISQUAD_HALL_MAP,
    WEEKEND_XLSX,
    WEEKEND_HALL_MAP,
    EXTRA_EVENTS_CSV_URL,
    EXTRA_HALL_MAP,
    EXTRA_TYPE_MAP,
)


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


def clean_text(value: object) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def normalize_key(value: object) -> str:
    return clean_text(value).upper()


def make_id(prefix: str, *parts: object) -> str:
    raw = "|".join(str(part) for part in parts)
    digest = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    return f"{prefix}-{digest}"


def to_iso(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%dT%H:%M:%S")


def parse_date(value: object) -> Optional[date]:
    text = clean_text(value)

    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            pass

    return None


def parse_time(value: object) -> Optional[time]:
    text = clean_text(value)
    text = text.replace(" Uhr", "").replace("Uhr", "").replace(".", ":").strip()

    match = re.search(r"(\d{1,2}):(\d{2})", text)

    if not match:
        return None

    hour = int(match.group(1))
    minute = int(match.group(2))

    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        return None

    return time(hour, minute)


# =========================================================
# MISQUAD
# =========================================================

XLSX_NS = {
    "m": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
}


def parse_misquad_datetime(value: object) -> Optional[datetime]:
    text = clean_text(value)

    if not text:
        return None

    try:
        return datetime.fromisoformat(text)
    except ValueError:
        pass

    for fmt in (
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d %H:%M",
        "%d.%m.%Y %H:%M",
    ):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            pass

    try:
        excel_number = float(text)
        return datetime(1899, 12, 30) + timedelta(days=excel_number)
    except ValueError:
        return None


def xlsx_column_number(cell_ref: str) -> int:
    match = re.match(r"([A-Z]+)", cell_ref or "")

    if not match:
        return 0

    number = 0

    for char in match.group(1):
        number = number * 26 + ord(char) - ord("A") + 1

    return number


def read_misquad_xlsx_rows(path: Path) -> list[dict[str, str]]:
    with zipfile.ZipFile(path) as archive:
        names = set(archive.namelist())

        worksheet_candidates = sorted(
            name
            for name in names
            if name.startswith("xl/worksheets/sheet") and name.endswith(".xml")
        )

        if not worksheet_candidates:
            raise ValueError("MISQUAD-Datei enthält kein Tabellenblatt.")

        worksheet_name = worksheet_candidates[0]

        shared_strings: list[str] = []

        if "xl/sharedStrings.xml" in names:
            shared_root = ET.fromstring(archive.read("xl/sharedStrings.xml"))

            for item in shared_root.findall("m:si", XLSX_NS):
                value = "".join(
                    node.text or ""
                    for node in item.findall(".//m:t", XLSX_NS)
                )
                shared_strings.append(value)

        sheet_root = ET.fromstring(archive.read(worksheet_name))
        raw_rows: list[dict[int, str]] = []

        for row in sheet_root.findall(".//m:sheetData/m:row", XLSX_NS):
            values: dict[int, str] = {}

            for cell in row.findall("m:c", XLSX_NS):
                column_number = xlsx_column_number(cell.get("r", ""))

                if column_number <= 0:
                    continue

                cell_type = cell.get("t", "")

                if cell_type == "inlineStr":
                    value = "".join(
                        node.text or ""
                        for node in cell.findall(".//m:is//m:t", XLSX_NS)
                    )
                else:
                    value_node = cell.find("m:v", XLSX_NS)
                    raw_value = value_node.text if value_node is not None else ""

                    if cell_type == "s" and raw_value:
                        try:
                            value = shared_strings[int(raw_value)]
                        except (ValueError, IndexError):
                            value = raw_value
                    else:
                        value = raw_value

                values[column_number] = clean_text(value)

            if values:
                raw_rows.append(values)

    if not raw_rows:
        raise ValueError("MISQUAD-Datei enthält keine Datenzeilen.")

    headers = {
        column: normalize_key(value)
        for column, value in raw_rows[0].items()
    }

    required_headers = {
        "DATUM",
        "WETTBEWERB",
        "KATEGORIE",
        "HEIMMANNSCHAFT",
        "ERGEBNIS",
        "GASTMANNSCHAFT",
        "HALLE",
        "STATUS",
    }

    missing_headers = required_headers - set(headers.values())

    if missing_headers:
        raise ValueError(
            "MISQUAD-Datei hat nicht das erwartete Format. Fehlende Spalten: "
            + ", ".join(sorted(missing_headers))
        )

    result: list[dict[str, str]] = []

    for raw_row in raw_rows[1:]:
        row = {
            header: clean_text(raw_row.get(column, ""))
            for column, header in headers.items()
        }

        if any(row.values()):
            result.append(row)

    return result


def load_misquad_games() -> list[CalendarEvent]:
    path = Path(MISQUAD_XLSX)

    if not path.exists():
        raise FileNotFoundError(
            f"MISQUAD-Datei fehlt: {MISQUAD_XLSX}"
        )

    rows = read_misquad_xlsx_rows(path)

    club_key = normalize_key(CLUB_NAME)

    hall_map = {
        normalize_key(name): hall_id
        for name, hall_id in MISQUAD_HALL_MAP.items()
    }

    events: list[CalendarEvent] = []
    seen: set[str] = set()
    skipped_halls: Counter[str] = Counter()
    invalid_rows = 0

    for row_no, row in enumerate(rows, start=2):
        home_team = clean_text(row.get("HEIMMANNSCHAFT", ""))
        guest_team = clean_text(row.get("GASTMANNSCHAFT", ""))

        if club_key not in normalize_key(home_team):
            continue

        start = parse_misquad_datetime(row.get("DATUM", ""))

        if not start:
            print(f"WARNING: MISQUAD Zeile {row_no}: Datum nicht lesbar")
            invalid_rows += 1
            continue

        if start.date() < DATE_FROM or start.date() > DATE_TO:
            continue

        if start.hour == 0 and start.minute == 0:
            print(f"WARNING: MISQUAD Zeile {row_no}: 00:00 Uhr übersprungen")
            invalid_rows += 1
            continue

        hall_raw = clean_text(row.get("HALLE", ""))
        hall_key = normalize_key(hall_raw)
        hall_id = hall_map.get(hall_key)

        if not hall_id:
            skipped_halls[hall_key or "<LEER>"] += 1
            continue

        if hall_id not in HALLS:
            continue

        competition = clean_text(row.get("WETTBEWERB", ""))
        category = clean_text(row.get("KATEGORIE", ""))
        status = clean_text(row.get("STATUS", ""))
        result = clean_text(row.get("ERGEBNIS", ""))

        end = start + timedelta(minutes=DEFAULT_GAME_DURATION_MINUTES)

        event_id = make_id(
            "misquad",
            start.isoformat(),
            home_team,
            guest_team,
            hall_id,
            competition,
        )

        if event_id in seen:
            continue

        seen.add(event_id)

        description_parts = ["Quelle: MISQUAD"]

        if competition:
            description_parts.append(f"Wettbewerb: {competition}")

        if category:
            description_parts.append(f"Kategorie: {category}")

        if status:
            description_parts.append(f"Status: {status}")

        if result and result != "-":
            description_parts.append(f"Ergebnis: {result}")

        hall = HALLS[hall_id]

        events.append(
            CalendarEvent(
                id=event_id,
                title=f"{home_team} - {guest_team}",
                start=to_iso(start),
                end=to_iso(end),
                hall_id=hall_id,
                hall=hall["name"],
                type="game",
                source="MISQUAD",
                location=hall["name"],
                description=" | ".join(description_parts),
                color=hall.get("color", ""),
            )
        )

    print(f"MISQUAD rows: {len(rows)}")
    print(f"MISQUAD hall games imported: {len(events)}")

    if skipped_halls:
        print("MISQUAD Heimspiele mit unbekannter Halle:")

        for hall_name, count in skipped_halls.most_common():
            print(f"  - {hall_name}: {count}")

    if invalid_rows:
        print(f"MISQUAD ungültige Zeilen: {invalid_rows}")

    return sorted(events, key=lambda event: event.start)


# =========================================================
# TRAINING
# =========================================================

def weekday_to_int(value: str) -> Optional[int]:
    mapping = {
        "MO": 0,
        "MON": 0,
        "MONTAG": 0,
        "DI": 1,
        "TU": 1,
        "TUE": 1,
        "DIENSTAG": 1,
        "MI": 2,
        "WE": 2,
        "WED": 2,
        "MITTWOCH": 2,
        "DO": 3,
        "TH": 3,
        "THU": 3,
        "DONNERSTAG": 3,
        "FR": 4,
        "FRI": 4,
        "FREITAG": 4,
        "SA": 5,
        "SAT": 5,
        "SAMSTAG": 5,
        "SO": 6,
        "SU": 6,
        "SUN": 6,
        "SONNTAG": 6,
    }

    return mapping.get(clean_text(value).upper())


def load_training_events() -> list[CalendarEvent]:
    path = Path(TRAINING_CSV)

    if not path.exists():
        print(f"training csv not found: {TRAINING_CSV}")
        return []

    events: list[CalendarEvent] = []

    with path.open("r", encoding="utf-8-sig", newline="") as file:
        reader = csv.DictReader(file)

        for row_no, row in enumerate(reader, start=2):
            if not any(clean_text(value) for value in row.values()):
                continue

            event_type = clean_text(row.get("type", "")) or "training"
            team = clean_text(row.get("team", "")) or "Training"
            hall_id = clean_text(row.get("hall_id", ""))

            weekday = weekday_to_int(row.get("weekday", ""))
            start_time = parse_time(row.get("start_time", ""))
            end_time = parse_time(row.get("end_time", ""))
            row_date_from = parse_date(row.get("date_from", ""))
            row_date_to = parse_date(row.get("date_to", ""))
            notes = clean_text(row.get("notes", ""))

            if hall_id not in HALLS:
                continue

            if (
                weekday is None
                or not start_time
                or not end_time
                or not row_date_from
                or not row_date_to
            ):
                continue

            valid_from = max(row_date_from, DATE_FROM)
            valid_to = min(row_date_to, DATE_TO)

            if valid_from > valid_to:
                continue

            current = valid_from

            while current.weekday() != weekday:
                current += timedelta(days=1)

            hall = HALLS[hall_id]

            while current <= valid_to:
                start_dt = datetime.combine(current, start_time)
                end_dt = datetime.combine(current, end_time)

                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)

                if event_type == "training":
                    title = f"Training {team}"
                elif event_type == "blocked":
                    title = f"Belegt: {team}"
                else:
                    title = team

                events.append(
                    CalendarEvent(
                        id=make_id(
                            "training",
                            event_type,
                            team,
                            hall_id,
                            current,
                            start_time,
                            end_time,
                        ),
                        title=title,
                        start=to_iso(start_dt),
                        end=to_iso(end_dt),
                        hall_id=hall_id,
                        hall=hall["name"],
                        type=event_type,
                        source="trainings.csv",
                        location=hall["name"],
                        description=notes,
                        color=hall.get("color", ""),
                    )
                )

                current += timedelta(days=7)

    print(f"training events: {len(events)}")
    return events


# =========================================================
# WOCHENEND-EXCEL
# =========================================================

def excel_cell_text(value: object) -> str:
    if value is None:
        return ""

    return clean_text(value)


def parse_excel_date(value: object) -> Optional[date]:
    if isinstance(value, datetime):
        return value.date()

    if isinstance(value, date):
        return value

    text = excel_cell_text(value)

    match = re.search(r"(\d{1,2}\.\d{1,2}\.\d{2,4})", text)

    if match:
        return parse_date(match.group(1))

    return parse_date(text)


def parse_excel_time_range(
    value: object
) -> tuple[Optional[time], Optional[time]]:
    text = excel_cell_text(value)

    matches = re.findall(r"(\d{1,2})[:.](\d{2})", text)

    if len(matches) < 2:
        return None, None

    start = time(int(matches[0][0]), int(matches[0][1]))
    end = time(int(matches[1][0]), int(matches[1][1]))

    return start, end


def load_weekend_excel_events() -> list[CalendarEvent]:
    if not WEEKEND_XLSX:
        return []

    path = Path(WEEKEND_XLSX)

    if not path.exists():
        print(f"weekend excel not found: {WEEKEND_XLSX}")
        return []

    if load_workbook is None:
        return []

    workbook = load_workbook(path, data_only=True)

    events: list[CalendarEvent] = []

    for sheet in workbook.worksheets:
        current_date: Optional[date] = None
        hall_columns: dict[int, str] = {}

        for row in sheet.iter_rows():
            values = [cell.value for cell in row]

            first_value = values[0] if values else None
            possible_date = parse_excel_date(first_value)

            if possible_date:
                current_date = possible_date

            for index, value in enumerate(values):
                text = excel_cell_text(value)

                if text in WEEKEND_HALL_MAP:
                    hall_columns[index] = WEEKEND_HALL_MAP[text]

            if not current_date:
                continue

            for col_index, hall_id in hall_columns.items():
                if hall_id not in HALLS:
                    continue

                time_col_index = max(0, col_index - 2)

                time_value = (
                    values[time_col_index]
                    if time_col_index < len(values)
                    else None
                )

                title_value = (
                    values[col_index]
                    if col_index < len(values)
                    else None
                )

                title = excel_cell_text(title_value)

                if not title or title in WEEKEND_HALL_MAP:
                    continue

                start_time, end_time = parse_excel_time_range(time_value)

                if not start_time or not end_time:
                    continue

                if current_date < DATE_FROM or current_date > DATE_TO:
                    continue

                start_dt = datetime.combine(current_date, start_time)
                end_dt = datetime.combine(current_date, end_time)

                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)

                hall = HALLS[hall_id]

                events.append(
                    CalendarEvent(
                        id=make_id(
                            "weekend",
                            sheet.title,
                            current_date,
                            hall_id,
                            start_time,
                            end_time,
                            title,
                        ),
                        title=title,
                        start=to_iso(start_dt),
                        end=to_iso(end_dt),
                        hall_id=hall_id,
                        hall=hall["name"],
                        type="weekend",
                        source="weekend excel",
                        location=hall["name"],
                        description=f"Quelle: {WEEKEND_XLSX}",
                        color=hall.get("color", ""),
                    )
                )

    print(f"weekend excel events: {len(events)}")
    return events


# =========================================================
# GOOGLE-FORM-ZUSATZTERMINE
# =========================================================

def get_row_value(row: dict[str, str], names: list[str]) -> str:
    normalized = {
        clean_text(key).lower(): value
        for key, value in row.items()
    }

    for name in names:
        key = clean_text(name).lower()

        if key in normalized:
            return clean_text(normalized[key])

    return ""


def load_extra_events() -> list[CalendarEvent]:
    if not EXTRA_EVENTS_CSV_URL:
        return []

    try:
        response = requests.get(EXTRA_EVENTS_CSV_URL, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        print(f"WARNING: extra events fetch failed: {exc}")
        return []

    text = response.text

    if "<html" in text.lower():
        print("WARNING: extra events URL returned HTML")
        return []

    reader = csv.DictReader(io.StringIO(text))
    events: list[CalendarEvent] = []

    for row_no, row in enumerate(reader, start=2):
        title = get_row_value(row, ["Titel", "title", "Name", "Termin"]) or "Zusatztermin"
        hall_name = get_row_value(row, ["Halle", "hall", "Sporthalle"])
        date_raw = get_row_value(row, ["Datum", "date"])
        start_raw = get_row_value(row, ["Startzeit", "Start", "Beginn"])
        end_raw = get_row_value(row, ["Endzeit", "Ende"])
        type_raw = get_row_value(row, ["Art", "Typ", "type"])
        notes = get_row_value(row, ["Notiz", "Notizen", "Beschreibung", "Info"])

        hall_id = EXTRA_HALL_MAP.get(hall_name)

        if not hall_id or hall_id not in HALLS:
            continue

        event_date = parse_date(date_raw)
        start_time = parse_time(start_raw)
        end_time = parse_time(end_raw)

        if not event_date or not start_time or not end_time:
            continue

        if event_date < DATE_FROM or event_date > DATE_TO:
            continue

        start_dt = datetime.combine(event_date, start_time)
        end_dt = datetime.combine(event_date, end_time)

        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        event_type = EXTRA_TYPE_MAP.get(type_raw, "event")
        hall = HALLS[hall_id]

        events.append(
            CalendarEvent(
                id=make_id(
                    "extra",
                    title,
                    hall_id,
                    event_date,
                    start_time,
                    end_time,
                    notes,
                ),
                title=title,
                start=to_iso(start_dt),
                end=to_iso(end_dt),
                hall_id=hall_id,
                hall=hall["name"],
                type=event_type,
                source="Google Form",
                location=hall["name"],
                description=notes,
                color=hall.get("color", ""),
            )
        )

    print(f"extra events: {len(events)}")
    return events


# =========================================================
# JSON + ICAL
# =========================================================

def escape_ics_text(value: str) -> str:
    value = str(value or "")
    value = value.replace("\\", "\\\\")
    value = value.replace("\n", "\\n")
    value = value.replace(",", "\\,")
    value = value.replace(";", "\\;")
    return value


def format_ics_datetime(value: str) -> str:
    dt = datetime.fromisoformat(value)
    return dt.strftime("%Y%m%dT%H%M%S")


def write_ics(path: Path, events: list[CalendarEvent], calendar_name: str) -> None:
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//HSG FONA//Hallenkalender//DE",
        "CALSCALE:GREGORIAN",
        "METHOD:PUBLISH",
        f"X-WR-CALNAME:{escape_ics_text(calendar_name)}",
        f"X-WR-TIMEZONE:{TIMEZONE}",
    ]

    now = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    for event in events:
        lines.extend(
            [
                "BEGIN:VEVENT",
                f"UID:{event.id}@hsg-fona.github.io",
                f"DTSTAMP:{now}",
                f"DTSTART;TZID={TIMEZONE}:{format_ics_datetime(event.start)}",
                f"DTEND;TZID={TIMEZONE}:{format_ics_datetime(event.end)}",
                f"SUMMARY:{escape_ics_text(event.title)}",
                f"LOCATION:{escape_ics_text(event.location or event.hall)}",
                f"DESCRIPTION:{escape_ics_text(event.description)}",
                "END:VEVENT",
            ]
        )

    lines.append("END:VCALENDAR")

    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")


def write_json(path: Path, events: list[CalendarEvent]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)

    path.write_text(
        json.dumps(
            [asdict(event) for event in events],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


# =========================================================
# START
# =========================================================

def main() -> None:
    print(f"calendar import: {DATE_FROM.isoformat()} bis {DATE_TO.isoformat()}")

    games = load_misquad_games()
    trainings = load_training_events()
    weekend_events = load_weekend_excel_events()
    extra_events = load_extra_events()

    events = games + trainings + weekend_events + extra_events
    events = sorted(events, key=lambda event: event.start)

    print(f"events total: {len(events)}")

    write_json(Path("data/events.json"), events)

    write_ics(
        Path("calendars/gesamt.ics"),
        events,
        "HSG FONA Hallenkalender Gesamt",
    )

    for hall_id, hall in HALLS.items():
        hall_events = [
            event
            for event in events
            if event.hall_id == hall_id
        ]

        slug = hall.get("slug", hall_id)

        write_ics(
            Path("calendars") / f"{slug}.ics",
            hall_events,
            f"HSG FONA {hall['name']}",
        )

        print(f"ics {hall['name']}: {len(hall_events)} events")

    print("calendar import finished")


if __name__ == "__main__":
    main()
