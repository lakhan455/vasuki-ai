from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any

import httpx


WEATHERAPI_PUBLIC_URL = "https://www.weatherapi.com/"
DEFAULT_BASE_URL = "https://api.weatherapi.com/v1"

_WEATHER_SIGNAL = re.compile(
    r"\b(?:weather|mausam|temperature|temp|forecast|rain|raining|barish|baarish|"
    r"humidity|wind|aqi|air quality|pollution|weather alert|storm warning|"
    r"sunrise|sunset|moonrise|moonset|astronomy|timezone|time zone)\b",
    re.I,
)
_FUTURE_SIGNAL = re.compile(
    r"\b(?:forecast|tomorrow|kal|next\s+\d+\s+days?|next week|"
    r"will it rain|barish hogi|baarish hogi|rain tomorrow)\b",
    re.I,
)
_ALERT_SIGNAL = re.compile(
    r"\b(?:weather alert|alerts?|warning|storm warning|cyclone warning|"
    r"severe weather|thunderstorm warning)\b",
    re.I,
)
_AQI_SIGNAL = re.compile(
    r"\b(?:aqi|air quality|pollution|pm2\.?5|pm10)\b",
    re.I,
)
_ASTRONOMY_SIGNAL = re.compile(
    r"\b(?:sunrise|sunset|moonrise|moonset|moon phase|astronomy)\b",
    re.I,
)
_TIMEZONE_SIGNAL = re.compile(
    r"\b(?:timezone|time zone)\b",
    re.I,
)
_NEAR_ME = re.compile(
    r"\b(?:here|near me|my location|current location|mere yaha|mere yahaan)\b",
    re.I,
)

_LOCATION_PATTERNS = (
    re.compile(
        r"\b(?:weather|mausam|temperature|temp|forecast|rain|barish|baarish|"
        r"humidity|wind|aqi|air quality|sunrise|sunset|timezone|time zone)"
        r"\s+(?:in|at|for|of)\s+(.+?)(?:[?.!,]|$)",
        re.I,
    ),
    re.compile(
        r"^\s*(.+?)\s+(?:ka|ki|ke)\s+"
        r"(?:weather|mausam|temperature|temp|forecast|aqi|air quality)"
        r"(?:[?.!,]|\s|$)",
        re.I,
    ),
    re.compile(
        r"\b(?:today|tomorrow|aaj|kal)\s+(.+?)\s+"
        r"(?:me|mein|in)\s+(?:barish|baarish|rain|weather|mausam)"
        r"(?:[?.!,]|\s|$)",
        re.I,
    ),
    re.compile(
        r"^\s*(.+?)\s+(?:me|mein)\s+(?:barish|baarish|rain)\s+"
        r"(?:hogi|hoga|hai|ho rahi|ho raha|will|expected)",
        re.I,
    ),
    re.compile(
        r"^\s*(.+?)\s+(?:weather|forecast|temperature|temp|aqi)"
        r"(?:[?.!,]|\s|$)",
        re.I,
    ),
)


class WeatherAPIError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class WeatherIntent:
    version: str
    matched: bool
    operation: str
    location: str
    days: int
    include_aqi: bool
    include_alerts: bool
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _clean_location(value: str) -> str:
    text = " ".join(str(value or "").split()).strip(" ?.,!;:")
    text = re.sub(
        r"\b(?:for\s+)?(?:next\s+)?\d{1,2}\s+(?:day|days|din)\b.*$",
        "",
        text,
        flags=re.I,
    ).strip(" ?.,!;:")
    text = re.sub(
        r"\bnext\s+week\b.*$",
        "",
        text,
        flags=re.I,
    ).strip(" ?.,!;:")
    text = re.sub(
        r"\b(?:kya|kaisa|kesa|hai|hoga|hogi|today|tomorrow|aaj|kal|please|pls)\b.*$",
        "",
        text,
        flags=re.I,
    ).strip(" ?.,!;:")
    if _NEAR_ME.search(text):
        return ""
    return text[:120]


def _extract_location(text: str) -> str:
    if _NEAR_ME.search(text):
        return ""
    for pattern in _LOCATION_PATTERNS:
        match = pattern.search(text)
        if match:
            location = _clean_location(match.group(1))
            if location:
                return location
    return ""


def _forecast_days(text: str) -> int:
    low = text.casefold()
    numeric = re.search(
        r"\b(?:next\s+)?(\d{1,2})\s+(?:day|days|din)\b",
        low,
    )
    if numeric:
        return max(1, min(14, int(numeric.group(1))))
    if "next week" in low:
        return 7
    if "tomorrow" in low or re.search(r"\bkal\b", low):
        return 2
    return 3


def detect_weather_intent(text: str) -> WeatherIntent:
    prompt = " ".join(str(text or "").split()).strip()
    if not prompt or not _WEATHER_SIGNAL.search(prompt):
        return WeatherIntent(
            version="v41",
            matched=False,
            operation="none",
            location="",
            days=1,
            include_aqi=False,
            include_alerts=False,
            reason="no-weather-signal",
        )

    include_aqi = bool(_AQI_SIGNAL.search(prompt))
    include_alerts = bool(_ALERT_SIGNAL.search(prompt))

    if _ASTRONOMY_SIGNAL.search(prompt):
        operation = "astronomy"
    elif _TIMEZONE_SIGNAL.search(prompt):
        operation = "timezone"
    elif include_alerts and not _FUTURE_SIGNAL.search(prompt):
        operation = "alerts"
    elif _FUTURE_SIGNAL.search(prompt) or include_alerts:
        operation = "forecast"
    else:
        operation = "current"

    return WeatherIntent(
        version="v41",
        matched=True,
        operation=operation,
        location=_extract_location(prompt),
        days=_forecast_days(prompt) if operation == "forecast" else 1,
        include_aqi=include_aqi,
        include_alerts=include_alerts,
        reason="dedicated-live-weather-intent",
    )


def weatherapi_configured(settings: Any) -> bool:
    return bool(str(getattr(settings, "weatherapi_key", "") or "").strip())


def _base_url(settings: Any) -> str:
    value = str(
        getattr(settings, "weatherapi_base_url", DEFAULT_BASE_URL)
        or DEFAULT_BASE_URL
    ).strip()
    return value.rstrip("/")


def _timeout(settings: Any) -> float:
    try:
        value = float(getattr(settings, "weatherapi_timeout_seconds", 9.0))
    except (TypeError, ValueError):
        value = 9.0
    return max(3.0, min(20.0, value))


def _safe_error(payload: Any, status_code: int) -> WeatherAPIError:
    message = ""
    code = ""
    if isinstance(payload, dict):
        error = payload.get("error")
        if isinstance(error, dict):
            message = str(error.get("message") or "").strip()
            code = str(error.get("code") or "").strip()
    detail = message[:300] or f"HTTP {status_code}"
    if code:
        detail = f"{detail} (code {code})"
    return WeatherAPIError(f"WeatherAPI request failed: {detail}")


def _endpoint(operation: str) -> str:
    return {
        "current": "current.json",
        "forecast": "forecast.json",
        "alerts": "alerts.json",
        "astronomy": "astronomy.json",
        "timezone": "timezone.json",
        "search": "search.json",
    }.get(operation, "current.json")


async def fetch_weather(
    settings: Any,
    *,
    location: str,
    operation: str = "current",
    days: int = 3,
    include_aqi: bool = False,
    include_alerts: bool = False,
) -> dict[str, Any] | list[dict[str, Any]]:
    key = str(getattr(settings, "weatherapi_key", "") or "").strip()
    if not key:
        raise WeatherAPIError("WeatherAPI is not configured.")

    query = " ".join(str(location or "").split()).strip()
    if not query:
        raise WeatherAPIError(
            "A location is required. Vasuki will not use server IP as the user's location."
        )

    params: dict[str, str] = {
        "key": key,
        "q": query[:160],
    }
    if operation == "forecast":
        params["days"] = str(max(1, min(14, int(days or 3))))
        params["aqi"] = "yes" if include_aqi else "no"
        params["alerts"] = "yes" if include_alerts else "no"
    elif operation == "current":
        params["aqi"] = "yes" if include_aqi else "no"

    url = f"{_base_url(settings)}/{_endpoint(operation)}"
    timeout = httpx.Timeout(
        connect=min(5.0, _timeout(settings)),
        read=_timeout(settings),
        write=5.0,
        pool=5.0,
    )

    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.get(
                url,
                params=params,
                headers={
                    "Accept": "application/json",
                    "User-Agent": "Vasuki-AI-V41-Weather/1.0",
                },
            )
    except (httpx.TimeoutException, httpx.NetworkError) as exc:
        raise WeatherAPIError(
            "WeatherAPI is temporarily unreachable."
        ) from exc

    try:
        payload = response.json()
    except Exception as exc:
        raise WeatherAPIError(
            "WeatherAPI returned a non-JSON response."
        ) from exc

    if response.is_error:
        raise _safe_error(payload, response.status_code)

    if isinstance(payload, dict) and isinstance(payload.get("error"), dict):
        raise _safe_error(payload, response.status_code)

    if not isinstance(payload, (dict, list)):
        raise WeatherAPIError("WeatherAPI returned an unexpected payload.")

    return payload


def _condition(value: Any) -> str:
    if isinstance(value, dict):
        return str(value.get("text") or "").strip()
    return ""


def compact_weather_payload(
    payload: dict[str, Any] | list[dict[str, Any]],
    *,
    operation: str,
) -> dict[str, Any] | list[dict[str, Any]]:
    if isinstance(payload, list):
        return [
            {
                "name": item.get("name"),
                "region": item.get("region"),
                "country": item.get("country"),
                "lat": item.get("lat"),
                "lon": item.get("lon"),
            }
            for item in payload[:10]
            if isinstance(item, dict)
        ]

    location = payload.get("location") or {}
    compact_location = {
        "name": location.get("name"),
        "region": location.get("region"),
        "country": location.get("country"),
        "lat": location.get("lat"),
        "lon": location.get("lon"),
        "tz_id": location.get("tz_id"),
        "localtime": location.get("localtime"),
    }

    if operation == "timezone":
        return {"location": compact_location}

    if operation == "astronomy":
        astro = (payload.get("astronomy") or {}).get("astro") or {}
        return {
            "location": compact_location,
            "astronomy": {
                "sunrise": astro.get("sunrise"),
                "sunset": astro.get("sunset"),
                "moonrise": astro.get("moonrise"),
                "moonset": astro.get("moonset"),
                "moon_phase": astro.get("moon_phase"),
                "moon_illumination": astro.get("moon_illumination"),
            },
        }

    if operation == "alerts":
        alerts = (payload.get("alerts") or {}).get("alert") or []
        return {
            "location": compact_location,
            "alerts": [
                {
                    "headline": item.get("headline"),
                    "event": item.get("event"),
                    "severity": item.get("severity"),
                    "urgency": item.get("urgency"),
                    "areas": item.get("areas"),
                    "effective": item.get("effective"),
                    "expires": item.get("expires"),
                    "desc": str(item.get("desc") or "")[:1200],
                    "instruction": str(item.get("instruction") or "")[:900],
                }
                for item in alerts[:8]
                if isinstance(item, dict)
            ],
        }

    current = payload.get("current") or {}
    compact_current = {
        "last_updated": current.get("last_updated"),
        "temp_c": current.get("temp_c"),
        "feelslike_c": current.get("feelslike_c"),
        "condition": _condition(current.get("condition")),
        "wind_kph": current.get("wind_kph"),
        "wind_dir": current.get("wind_dir"),
        "pressure_mb": current.get("pressure_mb"),
        "precip_mm": current.get("precip_mm"),
        "humidity": current.get("humidity"),
        "cloud": current.get("cloud"),
        "vis_km": current.get("vis_km"),
        "uv": current.get("uv"),
    }
    if isinstance(current.get("air_quality"), dict):
        aq = current["air_quality"]
        compact_current["air_quality"] = {
            "co": aq.get("co"),
            "no2": aq.get("no2"),
            "o3": aq.get("o3"),
            "so2": aq.get("so2"),
            "pm2_5": aq.get("pm2_5"),
            "pm10": aq.get("pm10"),
            "us_epa_index": aq.get("us-epa-index"),
            "gb_defra_index": aq.get("gb-defra-index"),
        }

    result: dict[str, Any] = {
        "location": compact_location,
        "current": compact_current,
    }

    if operation == "forecast":
        days = []
        for item in (payload.get("forecast") or {}).get("forecastday") or []:
            if not isinstance(item, dict):
                continue
            day = item.get("day") or {}
            astro = item.get("astro") or {}
            days.append(
                {
                    "date": item.get("date"),
                    "max_temp_c": day.get("maxtemp_c"),
                    "min_temp_c": day.get("mintemp_c"),
                    "avg_temp_c": day.get("avgtemp_c"),
                    "max_wind_kph": day.get("maxwind_kph"),
                    "total_precip_mm": day.get("totalprecip_mm"),
                    "avg_visibility_km": day.get("avgvis_km"),
                    "avg_humidity": day.get("avghumidity"),
                    "daily_will_it_rain": day.get("daily_will_it_rain"),
                    "daily_chance_of_rain": day.get("daily_chance_of_rain"),
                    "condition": _condition(day.get("condition")),
                    "uv": day.get("uv"),
                    "sunrise": astro.get("sunrise"),
                    "sunset": astro.get("sunset"),
                }
            )
        result["forecast_days"] = days[:14]

        alerts = (payload.get("alerts") or {}).get("alert") or []
        if alerts:
            result["alerts"] = [
                {
                    "headline": item.get("headline"),
                    "event": item.get("event"),
                    "severity": item.get("severity"),
                    "urgency": item.get("urgency"),
                    "expires": item.get("expires"),
                }
                for item in alerts[:8]
                if isinstance(item, dict)
            ]

    return result


def build_weather_context(
    compact: dict[str, Any] | list[dict[str, Any]],
    *,
    operation: str,
) -> str:
    return (
        "VASUKI V41 LIVE WEATHER TOOL RESULT (WeatherAPI.com):\n"
        "Treat this structured external API result as the authoritative live weather "
        "evidence for this turn. Do not invent missing measurements. Mention the matched "
        "location and relevant update/date when useful. If the requested field is absent, "
        "say it was not returned by the configured WeatherAPI plan.\n"
        f"OPERATION: {operation}\n"
        "DATA:\n"
        + json.dumps(compact, ensure_ascii=False, separators=(",", ":"))[:18000]
    )


def weather_source(
    compact: dict[str, Any] | list[dict[str, Any]],
    *,
    operation: str,
) -> dict[str, Any]:
    entity = "weather"
    published = ""
    if isinstance(compact, dict):
        loc = compact.get("location") or {}
        entity = str(loc.get("name") or entity)
        current = compact.get("current") or {}
        published = str(
            current.get("last_updated")
            or loc.get("localtime")
            or ""
        )

    return {
        "title": f"WeatherAPI.com live {operation} data",
        "url": WEATHERAPI_PUBLIC_URL,
        "content": json.dumps(
            compact,
            ensure_ascii=False,
            separators=(",", ":"),
        )[:12000],
        "source_type": "weather-api",
        "entity": entity,
        "published_date": published or None,
        "provider": "weatherapi",
    }


def weather_coding_request(prompt: str) -> bool:
    low = str(prompt or "").casefold()
    weather = bool(_WEATHER_SIGNAL.search(low))
    coding = any(
        token in low
        for token in (
            "app", "website", "dashboard", "api", "backend", "frontend",
            "react", "next", "fastapi", "python", "project", "code",
            "build", "create", "implement", "integrate",
        )
    )
    return weather and coding


def weather_coding_guidance(prompt: str) -> str:
    if not weather_coding_request(prompt):
        return str(prompt or "")

    contract = """
VASUKI V41 WEATHERAPI INTEGRATION CONTRACT:
- Use WeatherAPI.com through HTTPS server-side requests.
- Keep WEATHERAPI_KEY backend-only in environment variables; never hardcode it or expose it in browser/client bundles.
- Default base URL: https://api.weatherapi.com/v1
- Use /current.json for current weather and /forecast.json for forecasts.
- Forecast days must stay between 1 and 14.
- Enable aqi=yes or alerts=yes only when the feature is needed.
- For browser apps, call WeatherAPI through the app's own backend/server route so the key remains private.
- Add .env.example with WEATHERAPI_KEY= but never a real key.
- Handle invalid location, rate limit/quota, provider 4xx/5xx, timeout, and unavailable-provider states clearly.
- Do not claim a live WeatherAPI request succeeded unless runtime evidence exists.
""".strip()

    return (
        f"{str(prompt or '').strip()}\n\n{contract}"
    )[:30000]


def weatherapi_health(settings: Any) -> dict[str, Any]:
    return {
        "version": "v41",
        "name": "Vasuki Live Weather Tool",
        "configured": weatherapi_configured(settings),
        "provider": "WeatherAPI.com",
        "base_url": _base_url(settings),
        "features": [
            "normal-chat-weather-intent-routing",
            "current-weather",
            "1-to-14-day-forecast",
            "weather-alerts",
            "air-quality",
            "astronomy",
            "timezone",
            "location-search",
            "existing-verified-web-fallback",
            "weather-app-coding-guidance",
        ],
        "api_key_exposed_to_frontend": False,
        "server_ip_used_as_user_location": False,
        "db_migration_required": False,
        "new_python_dependency_required": False,
        "automatic_external_side_effect": False,
    }
