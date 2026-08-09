from app.main_v8_phase3_part2 import app


def test_phase3_part2_health_route_registered():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/health/v8-phase3-part2" in paths
