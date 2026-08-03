from __future__ import annotations

import py_compile
import shutil
import sys
from datetime import datetime
from pathlib import Path


CEREBRAS_FUNCTION = r'''
async def chat_cerebras(
    messages: list[dict],
    settings: Settings,
    web_context: str = "",
    *,
    require_current: bool = False,
    as_of: str | None = None,
    temperature: float = 0.0,
) -> str:
    if not settings.cerebras_api_key:
        raise RuntimeError("CEREBRAS_API_KEY is not configured")

    base_url = settings.cerebras_base_url.rstrip("/")

    return await _openai_compatible(
        f"{base_url}/chat/completions",
        settings.cerebras_api_key,
        settings.cerebras_model,
        _openai_messages(
            messages,
            web_context,
            require_current=require_current,
            as_of=as_of,
        ),
        settings,
        temperature=temperature,
        token_field="max_completion_tokens",
    )


'''


def read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8-sig")


def write_text(path: Path, content: str) -> None:
    path.write_text(content, encoding="utf-8", newline="\n")


def require(condition: bool, message: str) -> None:
    if not condition:
        raise RuntimeError(message)


def replace_once(content: str, old: str, new: str, label: str) -> str:
    count = content.count(old)
    require(count == 1, f"{label}: expected exactly 1 match, found {count}.")
    return content.replace(old, new, 1)


def patch_config(path: Path) -> bool:
    content = read_text(path)
    if "cerebras_api_key:" in content:
        return False

    marker = '    sambanova_base_url: str = "https://api.sambanova.ai/v1"\n'
    require(marker in content, "config.py: SambaNova marker not found.")

    addition = (
        marker
        + '    cerebras_api_key: str | None = None\n'
        + '    cerebras_model: str = "gpt-oss-120b"\n'
        + '    cerebras_base_url: str = "https://api.cerebras.ai/v1"\n'
    )
    content = content.replace(marker, addition, 1)
    write_text(path, content)
    return True


def patch_chat(path: Path) -> bool:
    content = read_text(path)
    changed = False

    if "async def chat_cerebras(" not in content:
        marker = "async def chat_openrouter(\n"
        require(marker in content, "chat.py: chat_openrouter marker not found.")
        content = content.replace(marker, CEREBRAS_FUNCTION + marker, 1)
        changed = True

    old_provider_line = '    "sambanova": chat_sambanova,\n'
    new_provider_lines = (
        '    "sambanova": chat_sambanova,\n'
        '    "cerebras": chat_cerebras,\n'
    )
    if '"cerebras": chat_cerebras' not in content:
        content = replace_once(
            content,
            old_provider_line,
            new_provider_lines,
            "chat.py PROVIDERS",
        )
        changed = True

    old_verify = (
        'for name in '
        '("gemini", "groq", "sambanova", "openrouter", "mistral")'
    )
    new_verify = (
        'for name in '
        '("gemini", "groq", "cerebras", "sambanova", '
        '"openrouter", "mistral")'
    )
    if old_verify in content:
        content = replace_once(
            content,
            old_verify,
            new_verify,
            "chat.py verification order",
        )
        changed = True

    old_route = (
        'else ["groq", "sambanova", "gemini", '
        '"openrouter", "mistral"]'
    )
    new_route = (
        'else ["groq", "cerebras", "sambanova", "gemini", '
        '"openrouter", "mistral"]'
    )
    if old_route in content:
        content = replace_once(
            content,
            old_route,
            new_route,
            "chat.py fallback order",
        )
        changed = True

    require(
        '"cerebras": chat_cerebras' in content,
        "chat.py: Cerebras provider was not registered.",
    )
    require(
        new_route in content,
        "chat.py: Cerebras fallback order was not installed.",
    )

    if changed:
        write_text(path, content)
    return changed


def patch_schemas(path: Path) -> bool:
    content = read_text(path)
    if '"cerebras"' in content:
        return False

    marker = '        "sambanova",\n'
    replacement = '        "sambanova",\n        "cerebras",\n'
    content = replace_once(
        content,
        marker,
        replacement,
        "schemas.py ChatRequest provider",
    )
    write_text(path, content)
    return True


def patch_env_example(path: Path) -> bool:
    content = read_text(path)
    if "CEREBRAS_API_KEY=" in content:
        return False

    marker = "SAMBANOVA_BASE_URL=https://api.sambanova.ai/v1\n"
    require(marker in content, ".env.example: SambaNova base URL not found.")

    addition = (
        marker
        + "CEREBRAS_API_KEY=\n"
        + "CEREBRAS_MODEL=gpt-oss-120b\n"
        + "CEREBRAS_BASE_URL=https://api.cerebras.ai/v1\n"
    )
    content = content.replace(marker, addition, 1)
    write_text(path, content)
    return True


def patch_readme(path: Path) -> bool:
    if not path.exists():
        return False

    content = read_text(path)
    old = "Groq → SambaNova → Gemini → OpenRouter → Mistral"
    new = "Groq → Cerebras → SambaNova → Gemini → OpenRouter → Mistral"

    if old not in content:
        return False

    write_text(path, content.replace(old, new, 1))
    return True


def main() -> int:
    project_root = (
        Path(sys.argv[1]).expanduser().resolve()
        if len(sys.argv) > 1
        else Path.cwd().resolve()
    )

    targets = {
        "config": project_root / "backend" / "app" / "config.py",
        "chat": project_root / "backend" / "app" / "services" / "chat.py",
        "schemas": project_root / "backend" / "app" / "schemas.py",
        "env": project_root / "backend" / ".env.example",
        "readme": project_root / "README.md",
    }

    for name in ("config", "chat", "schemas", "env"):
        require(
            targets[name].exists(),
            f"Required file not found: {targets[name]}",
        )

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_dir = project_root / f"cerebras_patch_backup_{stamp}"
    backup_dir.mkdir(parents=True, exist_ok=False)

    for name in ("config", "chat", "schemas", "env", "readme"):
        source = targets[name]
        if source.exists():
            relative = source.relative_to(project_root)
            destination = backup_dir / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, destination)

    results = {
        "backend/app/config.py": patch_config(targets["config"]),
        "backend/app/services/chat.py": patch_chat(targets["chat"]),
        "backend/app/schemas.py": patch_schemas(targets["schemas"]),
        "backend/.env.example": patch_env_example(targets["env"]),
        "README.md": patch_readme(targets["readme"]),
    }

    for file_path in (
        targets["config"],
        targets["chat"],
        targets["schemas"],
    ):
        py_compile.compile(str(file_path), doraise=True)

    print("\nCerebras patch completed successfully.\n")
    for file_name, changed in results.items():
        print(f"{'[UPDATED]' if changed else '[ALREADY OK]'} {file_name}")

    print(f"\nBackup created at:\n{backup_dir}")
    print(
        "\nNext commands:\n"
        'git add backend/app/config.py backend/app/services/chat.py '
        'backend/app/schemas.py backend/.env.example README.md\n'
        'git commit -m "Add Cerebras chat provider"\n'
        "git push\n"
    )
    print(
        "Render Environment variables required:\n"
        "CEREBRAS_API_KEY=<your real key>\n"
        "CEREBRAS_MODEL=gpt-oss-120b\n"
        "CEREBRAS_BASE_URL=https://api.cerebras.ai/v1\n"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"\nPATCH FAILED: {exc}", file=sys.stderr)
        print(
            "No secret key was requested or stored by this script.",
            file=sys.stderr,
        )
        raise SystemExit(1)
