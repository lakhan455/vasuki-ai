from pathlib import Path
from types import SimpleNamespace

import pytest

from app.v41.weather_tool import (
    WeatherAPIError,
    build_weather_context,
    compact_weather_payload,
    detect_weather_intent,
    weather_coding_guidance,
    weather_coding_request,
    weather_source,
    weatherapi_configured,
    weatherapi_health,
)


def test_current_weather_intent():
    decision = detect_weather_intent("Jaipur weather kya hai?")
    assert decision.matched is True
    assert decision.operation == "current"
    assert decision.location.casefold() == "jaipur"


def test_hinglish_tomorrow_rain_intent():
    decision = detect_weather_intent("kal Jaipur me barish hogi?")
    assert decision.matched is True
    assert decision.operation == "forecast"
    assert decision.location.casefold() == "jaipur"
    assert decision.days == 2


def test_english_forecast_location_and_days():
    decision = detect_weather_intent("weather in New Delhi next 7 days")
    assert decision.operation == "forecast"
    assert decision.location.casefold() == "new delhi"
    assert decision.days == 7


def test_aqi_intent():
    decision = detect_weather_intent("AQI in Mumbai")
    assert decision.matched is True
    assert decision.include_aqi is True
    assert decision.location.casefold() == "mumbai"


def test_near_me_does_not_fake_location():
    decision = detect_weather_intent("weather near me")
    assert decision.matched is True
    assert decision.location == ""


def test_non_weather_query_is_not_intercepted():
    decision = detect_weather_intent("write a Python sorting function")
    assert decision.matched is False


def test_compact_current_payload():
    payload = {
        "location": {
            "name": "Jaipur",
            "region": "Rajasthan",
            "country": "India",
            "lat": 26.9,
            "lon": 75.8,
            "tz_id": "Asia/Kolkata",
            "localtime": "2026-08-25 10:30",
        },
        "current": {
            "last_updated": "2026-08-25 10:15",
            "temp_c": 29,
            "feelslike_c": 33,
            "condition": {"text": "Cloudy"},
            "humidity": 72,
            "wind_kph": 12,
        },
    }
    compact = compact_weather_payload(payload, operation="current")
    assert compact["location"]["name"] == "Jaipur"
    assert compact["current"]["temp_c"] == 29
    assert compact["current"]["condition"] == "Cloudy"


def test_forecast_compaction_keeps_rain_probability():
    payload = {
        "location": {"name": "Jaipur"},
        "current": {"condition": {"text": "Cloudy"}},
        "forecast": {
            "forecastday": [
                {
                    "date": "2026-08-26",
                    "day": {
                        "maxtemp_c": 31,
                        "mintemp_c": 25,
                        "daily_will_it_rain": 1,
                        "daily_chance_of_rain": 78,
                        "condition": {"text": "Moderate rain"},
                    },
                    "astro": {"sunrise": "06:02 AM", "sunset": "06:48 PM"},
                }
            ]
        },
    }
    compact = compact_weather_payload(payload, operation="forecast")
    day = compact["forecast_days"][0]
    assert day["daily_chance_of_rain"] == 78
    assert day["condition"] == "Moderate rain"


def test_weather_source_never_contains_key():
    compact = {
        "location": {"name": "Jaipur", "localtime": "2026-08-25 10:30"},
        "current": {"temp_c": 29, "last_updated": "2026-08-25 10:15"},
    }
    source = weather_source(compact, operation="current")
    assert source["url"] == "https://www.weatherapi.com/"
    assert "key=" not in source["url"].casefold()
    assert source["provider"] == "weatherapi"


def test_context_marks_data_as_external_live_evidence():
    context = build_weather_context(
        {"location": {"name": "Jaipur"}, "current": {"temp_c": 29}},
        operation="current",
        query="Jaipur ka weather kya hai?",
    )
    assert "LIVE WEATHER TOOL RESULT" in context
    assert "authoritative live weather evidence" in context
    assert "LATEST USER QUERY: Jaipur ka weather kya hai?" in context
    assert "Answer ONLY the latest user weather question" in context
    assert "Do NOT output Markdown images" in context
    assert "Do NOT manually create a Sources/Source/स्रोत section" in context

def test_weather_coding_guidance_is_backend_key_safe():
    prompt = "Build a React weather dashboard"
    assert weather_coding_request(prompt) is True
    enhanced = weather_coding_guidance(prompt)
    assert "WEATHERAPI_KEY" in enhanced
    assert "backend-only" in enhanced
    assert "/forecast.json" in enhanced


def test_non_weather_coding_prompt_not_changed():
    prompt = "Build a React todo app"
    assert weather_coding_guidance(prompt) == prompt


def test_health_does_not_expose_key():
    settings = SimpleNamespace(
        weatherapi_key="super-secret",
        weatherapi_base_url="https://api.weatherapi.com/v1",
    )
    health = weatherapi_health(settings)
    assert health["configured"] is True
    assert "super-secret" not in str(health)
    assert health["api_key_exposed_to_frontend"] is False


def test_configured_helper():
    assert weatherapi_configured(SimpleNamespace(weatherapi_key="x")) is True
    assert weatherapi_configured(SimpleNamespace(weatherapi_key="")) is False


def test_main_v11_v41_integration_present():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    assert "VASUKI_V41_LIVE_WEATHER_TOOL_INTEGRATION" in source
    assert "v10.legacy._web_context = _v41_web_context" in source
    assert "build_autonomous_project = _v41_build_autonomous_project" in source
    assert '@app.get("/health/v41")' in source
    assert '@app.get("/api/v41/weather/current")' in source
    assert '@app.get("/api/v41/weather/forecast")' in source


def test_config_contains_weatherapi_backend_settings():
    backend = Path(__file__).resolve().parents[1]
    config = (backend / "app" / "config.py").read_text(encoding="utf-8")
    assert "weatherapi_key: str | None = None" in config
    assert "weatherapi_timeout_seconds" in config


def test_env_example_has_placeholder_not_secret():
    backend = Path(__file__).resolve().parents[1]
    env = (backend / ".env.example").read_text(encoding="utf-8")
    assert "WEATHERAPI_KEY=" in env
    assert "WEATHERAPI_BASE_URL=https://api.weatherapi.com/v1" in env

def test_weather_context_blocks_cross_turn_noise_and_media():
    context = build_weather_context(
        {
            "location": {"name": "Jaipur", "localtime": "2026-08-25 11:00"},
            "astronomy": {"sunrise": "06:03 AM", "sunset": "06:54 PM"},
        },
        operation="astronomy",
        query="Jaipur ka sunrise aur sunset kab hai?",
    )
    assert "Earlier conversation turns are background only" in context
    assert "logos, favicons" in context
    assert "other questions" in context
    assert "Source metadata is rendered separately" in context


def test_main_v11_passes_latest_query_to_weather_context():
    backend = Path(__file__).resolve().parents[1]
    source = (backend / "app" / "main_v11.py").read_text(encoding="utf-8")
    start = source.index("async def _v41_web_context(")
    end = source.index("\n\nasync def _v41_build_autonomous_project(", start)
    assert "query=query," in source[start:end]
