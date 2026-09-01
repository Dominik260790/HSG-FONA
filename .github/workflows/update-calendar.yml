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
