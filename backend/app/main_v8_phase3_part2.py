from __future__ import annotations

from typing import Any

import app.main_v8_phase3 as phase3

app = phase3.app
settings = phase3.settings


@app.get("/health/v8-phase3-part2")
async def health_v8_phase3_part2() -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v8-phase3-part2",
        "regenerate_ui": True,
        "edit_resend_ui": True,
        "branch_safe_editing": True,
        "feedback_ui": True,
        "sidebar_workspaces": True,
        "authenticated_files_ui": True,
        "authenticated_images_ui": True,
        "authenticated_owner_ui": True,
        "authenticated_projects_ui": True,
    }
