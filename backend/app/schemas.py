"""Request/response models (mirrors api_contracts.md v1.0)."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator

Signal = Literal["weather", "holidays", "trends", "macro", "events", "marketplace"]
SIGNALS: tuple[str, ...] = ("weather", "holidays", "trends", "macro", "events", "marketplace")


# --- Profile ---------------------------------------------------------------
class ProfileUpsert(BaseModel):
    business_name: str | None = None
    country_code: str = Field(min_length=2, max_length=2)
    city: str | None = None
    latitude: float | None = Field(default=None, ge=-90, le=90)
    longitude: float | None = Field(default=None, ge=-180, le=180)
    timezone: str = "UTC"
    currency: str = Field(default="USD", min_length=3, max_length=3)

    @field_validator("country_code", "currency")
    @classmethod
    def upper(cls, v: str) -> str:
        return v.upper()


class Profile(ProfileUpsert):
    onboarding_complete: bool = True


# --- Uploads ---------------------------------------------------------------
class UploadAccepted(BaseModel):
    upload_id: str
    status: Literal["pending"] = "pending"
    status_url: str


class RowError(BaseModel):
    row: int
    field: str
    message: str


class UploadStatus(BaseModel):
    id: str
    kind: Literal["sales", "calendar"]
    status: Literal["pending", "validated", "loaded", "failed"]
    row_count: int | None = None
    error_report: dict | None = None
    created_at: datetime | None = None


# --- Products --------------------------------------------------------------
class ProductItem(BaseModel):
    sku: str
    product_name: str
    category: str | None = None
    sales_days: int = 0
    last_sale_date: date | None = None
    has_forecast: bool = False


class ProductList(BaseModel):
    items: list[ProductItem]
    total: int


# --- Forecasts -------------------------------------------------------------
class ForecastPoint(BaseModel):
    date: date
    yhat: float
    yhat_lower: float
    yhat_upper: float


class Factor(BaseModel):
    factor: str
    importance: float
    direction: Literal["up", "down", "neutral"] | None = None


class ForecastSeries(BaseModel):
    sku: str
    model_version: str
    mape_backtest: float | None = None
    degraded: bool = False
    points: list[ForecastPoint]
    factors: list[Factor] = []


class SignalHealth(BaseModel):
    signal: str
    status: Literal["live", "stale", "degraded", "disabled"]
    last_success_at: datetime | None = None
    quota_note: str | None = None


class ForecastResponse(BaseModel):
    model_run_id: str
    generated_at: datetime
    series: list[ForecastSeries]
    signal_health: list[SignalHealth] = []


# --- Sales -----------------------------------------------------------------
class SalesRow(BaseModel):
    date: date
    sku: str
    quantity: float
    revenue: float | None = None
    price: float | None = None
    promo_flag: bool = False


# --- Signal settings -------------------------------------------------------
class SignalSettingsPatch(BaseModel):
    model_config = {"extra": "forbid"}

    weather: bool | None = None
    holidays: bool | None = None
    trends: bool | None = None
    macro: bool | None = None
    events: bool | None = None
    marketplace: bool | None = None


class SignalSetting(BaseModel):
    signal: Signal
    enabled: bool


# --- Marketplace -----------------------------------------------------------
class AsinCreate(BaseModel):
    asin: str = Field(pattern=r"^[A-Z0-9]{10}$")


class AsinItem(BaseModel):
    asin: str
    created_at: datetime | None = None


# --- Calendar --------------------------------------------------------------
class CalendarEvent(BaseModel):
    id: int | None = None
    label: str
    start_date: date
    end_date: date


# --- Errors (RFC 7807-lite) ------------------------------------------------
class Problem(BaseModel):
    type: str = "about:blank"
    title: str
    status: int
    detail: str | None = None
    errors: list[dict] | None = None
