"""In-memory fake of the supabase-py fluent client used in unit/API tests.

Supports exactly the surface the app uses: table().select/insert/upsert/update/
delete + eq/in_/gte/lte/ilike/order/limit/range + execute() -> .data
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Conflict keys used by upserts (mirror DB PKs / unique constraints).
_CONFLICT_KEYS = {
    "profiles": ("id",),
    "products": ("user_id", "sku"),
    "sales_daily": ("user_id", "sku", "date"),
    "signal_settings": ("user_id", "signal"),
    "calendar_events": ("user_id", "label", "start_date"),
    "tracked_asins": ("user_id", "asin"),
    "forecasts": ("user_id", "sku", "forecast_date", "model_run_id"),
    "forecast_factors": ("user_id", "sku", "model_run_id", "factor"),
}

# Tables with identity columns the fake must auto-assign (Amendment 2).
_AUTO_ID_TABLES = {"calendar_events"}


@dataclass
class FakeResponse:
    data: list[dict]


class FakeQuery:
    def __init__(self, store: "FakeDb", table: str) -> None:
        self._store = store
        self._table = table
        self._mode = "select"
        self._payload: list[dict] | dict | None = None
        self._columns: list[str] | None = None
        self._filters: list[tuple[str, str, object]] = []
        self._order: tuple[str, bool] | None = None
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None
        self._on_conflict: str | None = None

    # --- operations ---------------------------------------------------------
    def select(self, columns: str = "*") -> "FakeQuery":
        self._mode = "select"
        self._columns = None if columns == "*" else [c.strip() for c in columns.split(",")]
        return self

    def insert(self, rows) -> "FakeQuery":
        self._mode = "insert"
        self._payload = rows if isinstance(rows, list) else [rows]
        return self

    def upsert(self, rows, on_conflict: str | None = None) -> "FakeQuery":
        self._mode = "upsert"
        self._payload = rows if isinstance(rows, list) else [rows]
        self._on_conflict = on_conflict
        return self

    def update(self, values: dict) -> "FakeQuery":
        self._mode = "update"
        self._payload = values
        return self

    def delete(self) -> "FakeQuery":
        self._mode = "delete"
        return self

    # --- filters ------------------------------------------------------------
    def eq(self, col: str, val) -> "FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col: str, vals: list) -> "FakeQuery":
        self._filters.append(("in", col, vals))
        return self

    def gte(self, col: str, val) -> "FakeQuery":
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col: str, val) -> "FakeQuery":
        self._filters.append(("lte", col, val))
        return self

    def ilike(self, col: str, pattern: str) -> "FakeQuery":
        self._filters.append(("ilike", col, pattern))
        return self

    def order(self, col: str, desc: bool = False) -> "FakeQuery":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "FakeQuery":
        self._limit = n
        return self

    def range(self, start: int, end: int) -> "FakeQuery":
        self._range = (start, end)
        return self

    # --- execution ------------------------------------------------------------
    def _rows(self) -> list[dict]:
        return self._store.tables.setdefault(self._table, [])

    def _matches(self, row: dict) -> bool:
        for op, col, val in self._filters:
            cell = row.get(col)
            if op == "eq" and cell != val:
                return False
            if op == "in" and cell not in val:
                return False
            if op == "gte" and (cell is None or str(cell) < str(val)):
                return False
            if op == "lte" and (cell is None or str(cell) > str(val)):
                return False
            if op == "ilike":
                needle = str(val).strip("%").lower()
                if needle not in str(cell or "").lower():
                    return False
        return True

    def execute(self) -> FakeResponse:
        rows = self._rows()
        if self._mode == "insert":
            rows.extend(self._store.assign_ids(self._table, self._payload))
            return FakeResponse(list(self._payload))
        if self._mode == "upsert":
            keys = tuple(self._on_conflict.split(",")) if self._on_conflict else (
                _CONFLICT_KEYS.get(self._table, ("id",))
            )
            for raw in self._payload:
                new = dict(raw)
                match = next(
                    (r for r in rows if all(str(r.get(k)) == str(new.get(k)) for k in keys)),
                    None,
                )
                if match is None:
                    rows.append(self._store.assign_ids(self._table, [new])[0])
                else:
                    match.update(new)
            return FakeResponse(list(self._payload))
        if self._mode == "update":
            matched = [r for r in rows if self._matches(r)]
            for r in matched:
                r.update(self._payload)
            return FakeResponse([dict(r) for r in matched])
        if self._mode == "delete":
            matched = [r for r in rows if self._matches(r)]
            self._store.tables[self._table] = [r for r in rows if not self._matches(r)]
            return FakeResponse([dict(r) for r in matched])

        result = [dict(r) for r in rows if self._matches(r)]
        if self._order:
            col, desc = self._order
            result.sort(key=lambda r: str(r.get(col) or ""), reverse=desc)
        if self._range:
            start, end = self._range
            result = result[start : end + 1]
        if self._limit is not None:
            result = result[: self._limit]
        if self._columns:
            result = [{c: r.get(c) for c in self._columns} for r in result]
        return FakeResponse(result)


@dataclass
class FakeDb:
    """Stand-in for the supabase client; seed tables directly in tests."""

    tables: dict[str, list[dict]] = field(default_factory=dict)

    def table(self, name: str) -> FakeQuery:
        return FakeQuery(self, name)

    def seed(self, table: str, rows: list[dict]) -> None:
        self.tables.setdefault(table, []).extend(self.assign_ids(table, rows))

    def assign_ids(self, table: str, rows) -> list[dict]:
        """Assign identity ids for tables that have them (mirrors DB identity cols)."""
        if isinstance(rows, dict):
            rows = [rows]
        if table not in _AUTO_ID_TABLES:
            return [dict(r) for r in rows]
        existing = self.tables.setdefault(table, [])
        next_id = max((r.get("id") or 0 for r in existing), default=0) + 1
        out = []
        for r in rows:
            r = dict(r)
            if r.get("id") is None:
                r["id"] = next_id
                next_id += 1
            out.append(r)
        return out


@dataclass
class FakeProducer:
    """Records published events for assertions."""

    events: list[tuple[str, str, dict]] = field(default_factory=list)

    def publish(self, topic: str, key: str, payload: dict) -> None:
        self.events.append((topic, key, payload))
