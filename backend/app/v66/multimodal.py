from __future__ import annotations

from typing import Any


def multimodal_capabilities(settings: Any) -> dict[str, Any]:
    server_stt = bool(
        str(getattr(settings, "v11_stt_api_base_url", "") or "").strip()
        and str(getattr(settings, "v11_stt_api_key", "") or "").strip()
    )
    server_tts = bool(
        str(getattr(settings, "v11_tts_api_base_url", "") or "").strip()
        and str(getattr(settings, "v11_tts_api_key", "") or "").strip()
    )

    return {
        "image_analysis": True,
        "image_editing": True,
        "pdf_analysis": True,
        "document_analysis": True,
        "audio_upload_transcription": server_stt,
        "server_text_to_speech": server_tts,
        "browser_voice_input": True,
        "browser_read_aloud": True,
        "joint_multimodal_endpoint": True,
        "max_joint_files": 8,
        "max_file_mb": 15,
        "notes": {
            "voice_input": (
                "Browser speech recognition is the primary zero-config path; "
                "server STT is available when configured."
            ),
            "read_aloud": (
                "Browser speech synthesis is available without exposing a backend key; "
                "server TTS remains optional."
            ),
        },
    }


def health_snapshot(settings: Any) -> dict[str, Any]:
    return {
        "ok": True,
        "version": "v66",
        "name": "Vasuki Multimodal & Voice Runtime",
        "capabilities": multimodal_capabilities(settings),
        "new_database_migration_required": False,
        "new_api_key_required_for_browser_voice": False,
    }
