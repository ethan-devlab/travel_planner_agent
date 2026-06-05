"""Weather and currency tools for Owner C."""

import datetime as dt
import logging
from decimal import Decimal, InvalidOperation

from django.conf import settings
from pydantic import BaseModel, Field

from app.views.exchange.exchange import currencies, get_exchange_rate
from app.views.weather.weather import WeatherLookupError, fetch_weather_and_forecast

from .common import planner_tool

logger = logging.getLogger(__name__)


class CurrencyConversionArgs(BaseModel):
    from_currency: str = Field(default="", description="Three-letter source currency code, such as USD.")
    to_currency: str = Field(default="", description="Three-letter target currency code, such as TWD.")
    amount: str | float | int = Field(default=0, description="Amount to convert. Must be zero or greater.")


@planner_tool
def lookup_weather(city="", date=""):
    """Look up current weather and a short forecast for a city."""
    tool_name = "lookup_weather"
    normalized_city = str(city or "").strip()
    normalized_date, date_error = _parse_optional_date(date)

    if not normalized_city:
        return _error(tool_name, "missing_city", "city is required.")
    if date_error:
        logger.warning("Owner C tool %s rejected invalid date input.", tool_name)
        return _error(tool_name, "invalid_date", "date must be YYYY-MM-DD when provided.")

    logger.info(
        "Owner C tool %s requested weather for city length %s and date provided=%s.",
        tool_name,
        len(normalized_city),
        bool(normalized_date),
    )
    try:
        weather_data, forecast_data = fetch_weather_and_forecast(normalized_city, settings.WEATHER_API_KEY)
    except WeatherLookupError as exc:
        logger.warning(
            "Owner C tool %s weather lookup failed for city length %s with %s.",
            tool_name,
            len(normalized_city),
            exc.__class__.__name__,
        )
        return _error(tool_name, "weather_lookup_failed", "Unable to retrieve weather information right now.")
    except Exception as exc:
        logger.warning(
            "Owner C tool %s weather provider raised %s for city length %s.",
            tool_name,
            exc.__class__.__name__,
            len(normalized_city),
        )
        return _error(tool_name, "weather_lookup_failed", "Unable to retrieve weather information right now.")

    target_label = normalized_date.strftime("%b %d") if normalized_date else None
    matching_forecasts = [
        _compact_forecast(entry)
        for entry in forecast_data
        if target_label is None or entry.get("date") == target_label
    ]
    if target_label is None:
        matching_forecasts = matching_forecasts[:5]

    logger.info(
        "Owner C tool %s returning %s forecast rows for city length %s.",
        tool_name,
        len(matching_forecasts),
        len(normalized_city),
    )
    return {
        "status": "ok",
        "tool": tool_name,
        "requested_inputs": {
            "city": normalized_city,
            "date": str(date or ""),
        },
        "normalized_values": {
            "city": weather_data.get("city", normalized_city),
            "date": normalized_date.isoformat() if normalized_date else "",
        },
        "current_weather": {
            "city": weather_data.get("city", normalized_city),
            "country": weather_data.get("country", ""),
            "temperature_c": weather_data.get("temperature"),
            "feels_like_c": weather_data.get("feels_like"),
            "description": weather_data.get("description", ""),
            "humidity": weather_data.get("humidity"),
            "wind_speed_kmh": weather_data.get("wind_speed"),
            "date_label": weather_data.get("date", ""),
            "time_label": weather_data.get("time", ""),
        },
        "forecast": matching_forecasts,
        "forecast_match_count": len(matching_forecasts),
        "available_forecast_dates": sorted({entry.get("date", "") for entry in forecast_data if entry.get("date")}),
    }


@planner_tool(args_schema=CurrencyConversionArgs)
def convert_currency(from_currency="", to_currency="", amount=0):
    """Convert an amount between supported currencies."""
    tool_name = "convert_currency"
    source_code = str(from_currency or "").strip().upper()
    target_code = str(to_currency or "").strip().upper()
    normalized_amount, amount_error = _parse_amount(amount)

    if not source_code or not target_code:
        return _error(tool_name, "missing_currency_code", "from_currency and to_currency are required.")
    if source_code not in currencies or target_code not in currencies:
        logger.warning("Owner C tool %s rejected unsupported currency pair %s/%s.", tool_name, source_code, target_code)
        return _error(tool_name, "unsupported_currency", "Only configured currency codes are supported.")
    if amount_error:
        logger.warning("Owner C tool %s rejected invalid amount for %s/%s.", tool_name, source_code, target_code)
        return _error(tool_name, "invalid_amount", "amount must be a non-negative number.")

    logger.info("Owner C tool %s requested pair %s/%s.", tool_name, source_code, target_code)
    try:
        rate = get_exchange_rate(source_code, target_code)
    except Exception as exc:
        logger.warning(
            "Owner C tool %s exchange lookup raised %s for pair %s/%s.",
            tool_name,
            exc.__class__.__name__,
            source_code,
            target_code,
        )
        return _error(tool_name, "exchange_lookup_failed", "Unable to retrieve exchange rate right now.")

    if isinstance(rate, Exception):
        logger.warning("Owner C tool %s exchange service returned provider error for pair %s/%s.", tool_name, source_code, target_code)
        return _error(tool_name, "exchange_lookup_failed", "Unable to retrieve exchange rate right now.")

    converted_amount = (normalized_amount * Decimal(str(rate))).quantize(Decimal("0.01"))
    return {
        "status": "ok",
        "tool": tool_name,
        "requested_inputs": {
            "from_currency": source_code,
            "to_currency": target_code,
            "amount": str(amount),
        },
        "normalized_values": {
            "from_currency": source_code,
            "to_currency": target_code,
            "amount": str(normalized_amount),
        },
        "exchange_rate": float(rate),
        "converted_amount": float(converted_amount),
        "converted_amount_display": f"{converted_amount:.2f}",
    }


def _compact_forecast(entry):
    return {
        "day": entry.get("day", ""),
        "date_label": entry.get("date", ""),
        "time_label": entry.get("time", ""),
        "temperature_c": entry.get("temperature"),
        "description": entry.get("description", ""),
        "humidity": entry.get("humidity"),
        "wind_speed_kmh": entry.get("wind_speed"),
        "precipitation_probability": entry.get("pop"),
    }


def _parse_optional_date(value):
    value = str(value or "").strip()
    if not value:
        return None, None
    try:
        return dt.date.fromisoformat(value), None
    except ValueError:
        return None, "invalid_date"


def _parse_amount(value):
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None, "invalid_amount"
    if amount < 0:
        return None, "invalid_amount"
    return amount, None


def _error(tool_name, error_code, message):
    return {
        "status": "error",
        "tool": tool_name,
        "error_code": error_code,
        "message": message,
    }


TOOLS = (
    lookup_weather,
    convert_currency,
)
