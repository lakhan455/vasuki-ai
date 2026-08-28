def test_v48_direct_routes_are_live_in_production_app():
    import app.main_v11 as production

    routes = {
        (
            getattr(route, "path", None),
            tuple(sorted(getattr(route, "methods", None) or ())),
        )
        for route in production.app.router.routes
    }

    required = {
        ("/health/v48", ("GET",)),
        ("/api/v48/tools", ("GET",)),
        ("/api/v48/data/analyze", ("POST",)),
        ("/api/v48/library/files", ("GET",)),
        ("/api/v48/library/files", ("POST",)),
        ("/api/v48/tasks", ("GET",)),
        ("/api/v48/tasks", ("POST",)),
    }

    missing = required - routes
    assert not missing, f"Missing V48 production routes: {sorted(missing)}"
