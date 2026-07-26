"""Calendar parser unit tests + calendar upload/list/delete API tests."""
import io

from app.services.calendar_parser import parse_calendar

ICS = b"""BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
SUMMARY:Summer Break
DTSTART:20260615
DTEND:20260801
END:VEVENT
BEGIN:VEVENT
SUMMARY:Winter Break
DTSTART:20261222;VALUE=DATE
DTEND:20270103
END:VEVENT
END:VCALENDAR
"""

CSV = b"""label,start_date,end_date
Summer Break,2026-06-15,2026-07-31
Bad Row,2026-13-99,2026-07-31
"""


def test_parse_ics_events():
    result = parse_calendar(ICS, "school.ics")
    assert result.errors == []
    assert len(result.events) == 2
    summer = result.events[0]
    assert summer["label"] == "Summer Break"
    assert summer["start_date"] == "2026-06-15"
    assert summer["end_date"] == "2026-07-31"  # DTEND exclusive -> inclusive


def test_parse_csv_events_with_bad_row():
    result = parse_calendar(CSV, "cal.csv")
    assert len(result.events) == 1
    assert result.errors[0]["field"] == "start_date"


def test_parse_csv_missing_headers():
    result = parse_calendar(b"a,b,c\n1,2,3\n", "cal.csv")
    assert result.events == []
    assert result.errors[0]["field"] == "header"


def test_calendar_upload_list_delete(onboarded_client, auth_headers):
    resp = onboarded_client.post(
        "/api/v1/uploads/calendar",
        files={"file": ("school.ics", io.BytesIO(ICS), "text/calendar")},
        headers=auth_headers,
    )
    assert resp.status_code == 202
    upload_id = resp.json()["upload_id"]
    assert onboarded_client.get(
        f"/api/v1/uploads/{upload_id}", headers=auth_headers
    ).json()["status"] == "loaded"

    events = onboarded_client.get("/api/v1/calendar/events", headers=auth_headers).json()
    first = events["items"][0]
    assert first["label"] == "Summer Break"
    assert first["id"] is not None

    resp = onboarded_client.delete(
        f"/api/v1/calendar/events/{first['id']}", headers=auth_headers
    )
    assert resp.status_code == 204
    remaining = onboarded_client.get("/api/v1/calendar/events", headers=auth_headers).json()
    assert len(remaining["items"]) == 1

    resp = onboarded_client.delete("/api/v1/calendar/events/999", headers=auth_headers)
    assert resp.status_code == 404
