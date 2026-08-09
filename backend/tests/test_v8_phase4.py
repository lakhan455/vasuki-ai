from app.main_v8_phase4 import app
from app.services.project_memory_v8 import normalize_project_memory


def test_project_memory_normalization():
    assert normalize_project_memory("  Keep   BLUE Theme  ") == "keep blue theme"


def test_phase4_routes_registered():
    paths = {getattr(route, "path", "") for route in app.routes}
    assert "/health/v8-phase4" in paths
    assert "/api/chat/search" in paths
    assert "/api/chat/branches/recent" in paths
    assert "/api/projects/{project_id}/memories" in paths
