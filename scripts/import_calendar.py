def parse_game_start(block: str) -> datetime | None:
    """Parse only the real handball.net game start.

    Important:
    - handball.net blocks can contain "letztes Update".
    - We must never use the update timestamp as event start.
    - Therefore only the part around "Spielbeginn" is accepted.
    """
    text = clean_text(block)

    # Ignore everything after "letztes Update".
    text = re.split(r"letztes\s+Update", text, flags=re.I)[0]

    # A real game must contain "Spielbeginn".
    if not re.search(r"Spielbeginn", text, flags=re.I):
        return None

    # Preferred pattern:
    # Spielbeginn Samstag, 13.09.2025 - 13:00 Uhr
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

    # Fallback:
    # Some text blocks may not keep "Spielbeginn" directly next to the date.
    # Still only search in the part before "letztes Update".
    match = re.search(
        r"(\d{1,2})\.(\d{1,2})\.(\d{4}).{0,80}?(\d{1,2}):(\d{2})",
        text,
        flags=re.I,
    )
    if match:
        d, m, y, hh, mm = map(int, match.groups())
        return datetime(y, m, d, hh, mm, tzinfo=BERLIN)

    return None


def extract_game_number(block: str, hall_id: str, start: datetime) -> str:
    match = re.search(r"Spielnummer\s*([0-9]+)", block, flags=re.I)
    if match:
        return match.group(1)

    return f"{hall_id}-{start:%Y%m%d%H%M}"


def extract_title(block: str) -> str:
    """Create a shorter title from the noisy handball.net text."""
    text = clean_text(block)

    # Only keep the part before schedule metadata.
    text = re.split(
        r"Spielbeginn|Spielnummer|Kalender abonnieren|letztes\s+Update|Halle",
        text,
        flags=re.I,
    )[0]

    # Remove dates and times.
    text = re.sub(r"\b(?:Mo|Di|Mi|Do|Fr|Sa|So)\.?,?\s*\d{1,2}\.\d{1,2}\.?", " ", text, flags=re.I)
    text = re.sub(r"\b\d{1,2}\.\d{1,2}\.\d{4}\b", " ", text)
    text = re.sub(r"\b\d{1,2}:\d{2}\b", " ", text)

    # Remove result if already played, e.g. "26 : 27".
    text = re.sub(r"\b\d{1,3}\s*:\s*\d{1,3}\b", " - ", text)

    # Normalize spacing around dash.
    text = re.sub(r"\s*-\s*", " - ", text)
    text = clean_text(text)

    # If the club name appears, start title there.
    # This removes a lot of competition/league noise before the teams.
    club_index = text.rfind(CLUB_NAME)
    if club_index >= 0:
        text = text[club_index:]

    text = clean_text(text)

    if not text:
        return "Handballspiel"

    return text[:140]


def fetch_handballnet_games() -> list[CalendarEvent]:
    """Fetch club schedule from handball.net and parse games safely.

    The important rule:
    only "Spielbeginn" may define the event start.
    "letztes Update" must never define the event start.
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

    text_blocks: list[str] = []

    # Whole page is too noisy, but nested divs are often duplicated.
    # We collect candidate blocks and deduplicate later by game number.
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

    events: list[CalendarEvent] = []
    seen: set[str] = set()

    for block in text_blocks:
        # Remove update text before parsing.
        block_without_update = re.split(r"letztes\s+Update", block, flags=re.I)[0]

        for hall_id, hall in HALLS.items():
            if hall_id not in block_without_update:
                continue

            start = parse_game_start(block_without_update)

            # Skip games without a clean start time.
            # A hall occupancy calendar should not import games without time.
            if not start:
                continue

            end = start + timedelta(minutes=DEFAULT_GAME_DURATION_MINUTES)

            game_no = extract_game_number(block_without_update, hall_id, start)
            event_id = f"handballnet-{game_no}"

            # handball.net often contains duplicate text blocks.
            if event_id in seen:
                continue

            seen.add(event_id)

            title = extract_title(block_without_update)

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
                description=f"Quelle: handball.net | {CLUB_NAME} | Hallennummer {hall_id} | Spielnummer {game_no}",
                url=url,
                color=hall.get("color", ""),
            ))

    return sorted(events, key=lambda e: e.start)
