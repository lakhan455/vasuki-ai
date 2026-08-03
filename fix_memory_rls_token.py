from __future__ import annotations

import shutil
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
AUTH = ROOT / "backend" / "app" / "auth.py"
MEMORY = ROOT / "backend" / "app" / "services" / "personal_memory.py"
MAIN = ROOT / "backend" / "app" / "main.py"


def replace_once(text: str, old: str, new: str, label: str) -> str:
    if new in text:
        print(f"[OK] {label}")
        return text
    if old not in text:
        raise RuntimeError(f"Patch location not found: {label}")
    print(f"[UPDATED] {label}")
    return text.replace(old, new, 1)


def backup() -> None:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    folder = ROOT / f"memory-token-fix-backup-{stamp}"
    for path in (AUTH, MEMORY, MAIN):
        destination = folder / path.relative_to(ROOT)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, destination)
    print(f"Backup: {folder}")


def patch_auth() -> None:
    text = AUTH.read_text(encoding="utf-8-sig")
    text = replace_once(
        text,
        'class AuthUser:\n    id: str\n    email: str | None = None\n',
        'class AuthUser:\n    id: str\n    email: str | None = None\n    access_token: str = ""\n',
        "AuthUser access token",
    )
    text = replace_once(
        text,
        '    user = AuthUser(\n'
        '        id=user_id,\n'
        '        email=(\n'
        '            str(payload.get("email"))\n'
        '            if payload.get("email")\n'
        '            else None\n'
        '        ),\n'
        '    )\n',
        '    user = AuthUser(\n'
        '        id=user_id,\n'
        '        email=(\n'
        '            str(payload.get("email"))\n'
        '            if payload.get("email")\n'
        '            else None\n'
        '        ),\n'
        '        access_token=token,\n'
        '    )\n',
        "Store verified access token",
    )
    AUTH.write_text(text, encoding="utf-8")


def patch_memory() -> None:
    text = MEMORY.read_text(encoding="utf-8-sig")
    text = replace_once(
        text,
        'def _headers(settings: Settings, *, representation: bool = False) -> dict[str, str]:\n'
        '    key = _server_key(settings)\n'
        '    headers = {\n'
        '        "apikey": key,\n'
        '        "Content-Type": "application/json",\n'
        '    }\n'
        '    if key and not key.startswith("sb_secret_"):\n'
        '        headers["Authorization"] = f"Bearer {key}"\n'
        '    if representation:\n'
        '        headers["Prefer"] = "return=representation"\n'
        '    return headers\n',
        'def _headers(\n'
        '    settings: Settings,\n'
        '    *,\n'
        '    representation: bool = False,\n'
        '    user_jwt: str | None = None,\n'
        ') -> dict[str, str]:\n'
        '    key = _server_key(settings)\n'
        '    headers = {\n'
        '        "apikey": key,\n'
        '        "Content-Type": "application/json",\n'
        '    }\n'
        '    if user_jwt:\n'
        '        headers["Authorization"] = f"Bearer {user_jwt}"\n'
        '    elif key and not key.startswith("sb_secret_"):\n'
        '        headers["Authorization"] = f"Bearer {key}"\n'
        '    if representation:\n'
        '        headers["Prefer"] = "return=representation"\n'
        '    return headers\n',
        "User-scoped Supabase headers",
    )

    replacements = [
        (
            'async def get_memory_enabled(user_id: str, settings: Settings) -> bool:\n',
            'async def get_memory_enabled(\n'
            '    user_id: str,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    user_jwt: str | None = None,\n'
            ') -> bool:\n',
            "get_memory_enabled token",
        ),
        (
            'async def set_memory_enabled(\n'
            '    user_id: str,\n'
            '    enabled: bool,\n'
            '    settings: Settings,\n'
            ') -> bool:\n',
            'async def set_memory_enabled(\n'
            '    user_id: str,\n'
            '    enabled: bool,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    user_jwt: str | None = None,\n'
            ') -> bool:\n',
            "set_memory_enabled token",
        ),
        (
            'async def list_user_memories(\n'
            '    user_id: str,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    limit: int = 50,\n'
            ') -> list[dict[str, Any]]:\n',
            'async def list_user_memories(\n'
            '    user_id: str,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    limit: int = 50,\n'
            '    user_jwt: str | None = None,\n'
            ') -> list[dict[str, Any]]:\n',
            "list_user_memories token",
        ),
        (
            'async def create_user_memory(\n'
            '    user_id: str,\n'
            '    memory_text: str,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    category: str = "preference",\n'
            ') -> dict[str, Any]:\n',
            'async def create_user_memory(\n'
            '    user_id: str,\n'
            '    memory_text: str,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    category: str = "preference",\n'
            '    user_jwt: str | None = None,\n'
            ') -> dict[str, Any]:\n',
            "create_user_memory token",
        ),
        (
            'async def delete_user_memory(\n'
            '    user_id: str,\n'
            '    memory_id: str,\n'
            '    settings: Settings,\n'
            ') -> None:\n',
            'async def delete_user_memory(\n'
            '    user_id: str,\n'
            '    memory_id: str,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    user_jwt: str | None = None,\n'
            ') -> None:\n',
            "delete_user_memory token",
        ),
        (
            'async def personal_memory_context(\n'
            '    user_id: str,\n'
            '    settings: Settings,\n'
            ') -> tuple[str, list[dict[str, Any]]]:\n',
            'async def personal_memory_context(\n'
            '    user_id: str,\n'
            '    settings: Settings,\n'
            '    *,\n'
            '    user_jwt: str | None = None,\n'
            ') -> tuple[str, list[dict[str, Any]]]:\n',
            "personal_memory_context token",
        ),
    ]
    for old, new, label in replacements:
        text = replace_once(text, old, new, label)

    text = text.replace(
        'headers=_headers(settings)',
        'headers=_headers(settings, user_jwt=user_jwt)',
    )
    text = replace_once(
        text,
        '            headers=_headers(settings, representation=True),\n',
        '            headers=_headers(\n'
        '                settings,\n'
        '                representation=True,\n'
        '                user_jwt=user_jwt,\n'
        '            ),\n',
        "Insert token header",
    )
    text = replace_once(
        text,
        '        rows = await list_user_memories(user_id, settings)\n',
        '        rows = await list_user_memories(\n'
        '            user_id,\n'
        '            settings,\n'
        '            user_jwt=user_jwt,\n'
        '        )\n',
        "Duplicate lookup token",
    )
    text = replace_once(
        text,
        '    enabled = await get_memory_enabled(user_id, settings)\n',
        '    enabled = await get_memory_enabled(\n'
        '        user_id,\n'
        '        settings,\n'
        '        user_jwt=user_jwt,\n'
        '    )\n',
        "Context settings token",
    )
    text = replace_once(
        text,
        '    rows = await list_user_memories(user_id, settings, limit=30)\n',
        '    rows = await list_user_memories(\n'
        '        user_id,\n'
        '        settings,\n'
        '        limit=30,\n'
        '        user_jwt=user_jwt,\n'
        '    )\n',
        "Context list token",
    )
    MEMORY.write_text(text, encoding="utf-8")


def patch_main() -> None:
    text = MAIN.read_text(encoding="utf-8-sig")
    text = replace_once(
        text,
        'async def _private_context(\n'
        '    *,\n'
        '    user_id: str,\n'
        '    query: str,\n'
        '    request: ChatRequest,\n'
        ') -> tuple[str, list[dict[str, Any]]]:\n',
        'async def _private_context(\n'
        '    *,\n'
        '    user_id: str,\n'
        '    access_token: str,\n'
        '    query: str,\n'
        '    request: ChatRequest,\n'
        ') -> tuple[str, list[dict[str, Any]]]:\n',
        "Private context access token",
    )
    text = replace_once(
        text,
        '                personal_memory_context(user_id, settings),\n',
        '                personal_memory_context(\n'
        '                    user_id,\n'
        '                    settings,\n'
        '                    user_jwt=access_token,\n'
        '                ),\n',
        "Private memory read token",
    )
    text = replace_once(
        text,
        '        get_memory_enabled(current_user.id, settings),\n'
        '        list_user_memories(current_user.id, settings),\n',
        '        get_memory_enabled(\n'
        '            current_user.id,\n'
        '            settings,\n'
        '            user_jwt=current_user.access_token,\n'
        '        ),\n'
        '        list_user_memories(\n'
        '            current_user.id,\n'
        '            settings,\n'
        '            user_jwt=current_user.access_token,\n'
        '        ),\n',
        "Memory list route token",
    )
    text = replace_once(
        text,
        '            category=request.category,\n'
        '        )\n',
        '            category=request.category,\n'
        '            user_jwt=current_user.access_token,\n'
        '        )\n',
        "Memory create route token",
    )
    text = replace_once(
        text,
        '            request.enabled,\n'
        '            settings,\n'
        '        )\n',
        '            request.enabled,\n'
        '            settings,\n'
        '            user_jwt=current_user.access_token,\n'
        '        )\n',
        "Memory settings route token",
    )
    text = replace_once(
        text,
        '        await delete_user_memory(current_user.id, memory_id, settings)\n',
        '        await delete_user_memory(\n'
        '            current_user.id,\n'
        '            memory_id,\n'
        '            settings,\n'
        '            user_jwt=current_user.access_token,\n'
        '        )\n',
        "Memory delete route token",
    )
    old = (
        '                explicit_memory,\n'
        '                settings,\n'
        '            )\n'
    )
    new = (
        '                explicit_memory,\n'
        '                settings,\n'
        '                user_jwt=current_user.access_token,\n'
        '            )\n'
    )
    if text.count(old) < 2:
        raise RuntimeError("Expected two explicit memory calls")
    text = text.replace(old, new)

    old = (
        '        user_id=current_user.id,\n'
        '        query=query,\n'
    )
    new = (
        '        user_id=current_user.id,\n'
        '        access_token=current_user.access_token,\n'
        '        query=query,\n'
    )
    if text.count(old) < 2:
        raise RuntimeError("Expected two private context calls")
    text = text.replace(old, new)

    text = replace_once(
        text,
        '            detail="Memory could not be saved.",\n',
        '            detail=f"Memory could not be saved: {str(exc)[:300]}",\n',
        "Expose safe memory error",
    )
    text = text.replace(
        '        except Exception:\n'
        '            answer = "Memory save nahi ho paayi. Thodi der baad dobara try karein."\n',
        '        except Exception as exc:\n'
        '            print("[memory] save failed:", type(exc).__name__, str(exc)[:500])\n'
        '            answer = "Memory save nahi ho paayi. Thodi der baad dobara try karein."\n',
    )
    MAIN.write_text(text, encoding="utf-8")


def main() -> None:
    missing = [str(path) for path in (AUTH, MEMORY, MAIN) if not path.exists()]
    if missing:
        raise SystemExit("Project files not found:\n" + "\n".join(missing))
    backup()
    patch_auth()
    patch_memory()
    patch_main()
    print("\nMemory RLS token fix applied successfully.")
    print("Next commands:")
    print("  py -m compileall backend/app")
    print("  git add backend/app/auth.py backend/app/main.py backend/app/services/personal_memory.py")
    print('  git commit -m "Fix personal memory RLS authentication"')
    print("  git push origin main")


if __name__ == "__main__":
    main()
