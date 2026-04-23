"""Shared Pydantic data models for the Flight Price Analyzer backend."""
from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field


# ── Search request ────────────────────────────────────────────────────────────

class ClassicSearchRequest(BaseModel):
    origin: str = Field(..., description="IATA city/airport code, e.g. LON")
    destination: str = Field(..., description="IATA city/airport code, e.g. BJS")
    dates: list[str] = Field(..., description="ISO date strings, e.g. ['2026-06-01']")
    cabin: Literal["Y", "C", "F"] = "Y"
    currency: Literal["EUR", "USD", "CNY", "GBP", "HKD"] = "EUR"
    trip_type: Literal["one_way", "round_trip"] = "one_way"
    return_dates: list[str] = Field(default_factory=list, description="For round_trip: return leg dates")
    weekday_filter: list[int] = Field(default_factory=list,
        description="Filter dates to specific weekdays: 0=Mon, 1=Tue, ..., 6=Sun. Empty = all days.")
    show_browser: bool = Field(False, description="Launch browser in visible (non-headless) mode")
    dry_run: bool = Field(False, description="Return mock data without hitting Trip.com")


# ── Flight result ─────────────────────────────────────────────────────────────

class FlightSegment(BaseModel):
    airline: str
    airline_code: str          # 2-letter IATA, e.g. CA
    flight_number: str         # e.g. CA855
    origin: str                # 3-letter airport code
    destination: str
    departure_time: str        # HH:MM
    arrival_time: str          # HH:MM (may include +1, +2 for next day)
    departure_date: str        # ISO date
    arrival_date: str
    aircraft: str = ""


class FlightResult(BaseModel):
    # Itinerary identity
    origin: str                # city IATA
    destination: str
    departure_date: str        # first leg date
    trip_type: str

    # Route info
    segments: list[FlightSegment]
    stops: int                 # 0 = direct
    is_direct: bool
    total_duration: str        # e.g. "10h 45m"

    # Main airline (for sorting/filtering)
    airline: str
    airline_code: str

    # Price
    price: float
    currency: str
    cabin: str

    # Meta
    scraped_at: str = ""
    source_url: str = ""


# ── SSE event payloads ────────────────────────────────────────────────────────

class ProgressEvent(BaseModel):
    type: Literal["progress"] = "progress"
    message: str
    current: int
    total: int


class ResultEvent(BaseModel):
    type: Literal["result"] = "result"
    date: str
    flights: list[FlightResult]
    cached: bool = False


class DoneEvent(BaseModel):
    type: Literal["done"] = "done"
    total_flights: int
    total_dates: int


class ErrorEvent(BaseModel):
    type: Literal["error"] = "error"
    message: str
    date: Optional[str] = None
