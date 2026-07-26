"""School-vacation / custom calendar parsing (ICS or CSV).

CSV format: ``label,start_date,end_date`` (ISO dates).
ICS: minimal VEVENT extraction (SUMMARY / DTSTART / DTEND) — no external dep.
"""
import csv
import io
from dataclasses import dataclass, field
from datetime import date, timedelta


@dataclass
class CalendarParseResult:
    events: list[dict] = field(default_factory=list)  # {label, start_date, end_date}
    errors: list[dict] = field(default_factory=list)


def _err(row_no: int, field_name: str, message: str) -> dict:
    return {"row": row_no, "field": field_name, "message": message}


def parse_calendar(content: bytes, filename: str) -> CalendarParseResult:
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError:
        return CalendarParseResult(errors=[_err(0, "file", "File is not valid UTF-8 text")])

    if filename.lower().endswith(".ics") or text.lstrip().startswith("BEGIN:VCALENDAR"):
        return _parse_ics(text)
    return _parse_csv(text)


def _parse_csv(text: str) -> CalendarParseResult:
    result = CalendarParseResult()
    reader = csv.DictReader(io.StringIO(text))
    headers = {h.strip().lower() for h in (reader.fieldnames or []) if h}
    if not {"label", "start_date", "end_date"} <= headers:
        result.errors.append(_err(1, "header", "Required columns: label,start_date,end_date"))
        return result
    for row_no, raw in enumerate(reader, start=2):
        row = {k.strip().lower(): (v or "").strip() for k, v in raw.items() if k}
        event = _validate_event(row_no, row.get("label", ""), row.get("start_date", ""),
                                row.get("end_date", ""), result.errors)
        if event:
            result.events.append(event)
    return result


def _parse_ics(text: str) -> CalendarParseResult:
    result = CalendarParseResult()
    summary: str | None = None
    start: str | None = None
    end: str | None = None
    row_no = 0

    def flush() -> None:
        nonlocal summary, start, end
        if summary and start:
            # ICS DTEND is exclusive; subtract one day for an inclusive range.
            end_adj = _ics_date(end)
            if end_adj:
                end_adj = (date.fromisoformat(end_adj) - timedelta(days=1)).isoformat()
            event = _validate_event(row_no, summary, _ics_date(start) or "", end_adj or "",
                                    result.errors)
            if event:
                result.events.append(event)
        summary = start = end = None

    in_event = False
    for row_no, line in enumerate(text.splitlines(), start=1):
        line = line.strip()
        if line == "BEGIN:VEVENT":
            in_event = True
        elif line == "END:VEVENT":
            flush()
            in_event = False
        elif in_event:
            if line.startswith("SUMMARY"):
                summary = line.split(":", 1)[-1].strip()
            elif line.startswith("DTSTART"):
                start = line.split(":", 1)[-1].strip()
            elif line.startswith("DTEND"):
                end = line.split(":", 1)[-1].strip()
    return result


def _ics_date(raw: str) -> str | None:
    digits = "".join(c for c in raw if c.isdigit())
    if len(digits) < 8:
        return None
    return f"{digits[0:4]}-{digits[4:6]}-{digits[6:8]}"


def _validate_event(row_no: int, label: str, start: str, end: str,
                    errors: list[dict]) -> dict | None:
    if not label:
        errors.append(_err(row_no, "label", "label is required"))
        return None
    try:
        start_d = date.fromisoformat(start)
    except ValueError:
        errors.append(_err(row_no, "start_date", "must be ISO YYYY-MM-DD"))
        return None
    try:
        end_d = date.fromisoformat(end) if end else start_d
    except ValueError:
        errors.append(_err(row_no, "end_date", "must be ISO YYYY-MM-DD"))
        return None
    if end_d < start_d:
        errors.append(_err(row_no, "end_date", "end_date must be >= start_date"))
        return None
    return {"label": label, "start_date": start_d.isoformat(), "end_date": end_d.isoformat()}
