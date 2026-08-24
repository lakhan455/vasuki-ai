import inspect

import app.main as legacy
import app.main_v5 as main_v5


def test_legacy_memory_symbol_remains_available_for_route_layers():
    assert callable(legacy.extract_explicit_memory)
    assert callable(legacy.extract_explicit_memory_command)


def test_v5_stream_uses_v18_2_memory_command_parser():
    source = inspect.getsource(main_v5.chat_stream_v5)

    assert "legacy.extract_explicit_memory_command(query)" in source
    assert "legacy.explicit_memory_category(explicit_memory)" in source
    assert "legacy._replace_last_user_content(" in source
    assert "memory_action_context" in source


def test_memory_plus_followup_splits_without_saving_question_as_memory():
    memory, followup = legacy.extract_explicit_memory_command(
        "Remember that my goal is to make Vasuki AI powerful. "
        "Now tell me what my goal is."
    )

    assert memory == "my goal is to make Vasuki AI powerful"
    assert followup == "Now tell me what my goal is."


def test_memory_only_still_supported():
    memory, followup = legacy.extract_explicit_memory_command(
        "Remember that I prefer concise answers."
    )

    assert memory == "I prefer concise answers"
    assert followup == ""
