from core.config import (
    CONFIG_TEMPLATE,
    Config,
    ensure_config,
    get_config_value,
    load_config,
    set_config,
)


def test_ensure_config_creates_full_template(tmp_path):
    path = tmp_path / "nested" / "config.ini"

    created_path, created = ensure_config(path)

    assert created is True
    assert created_path == path
    assert path.is_file()
    content = path.read_text(encoding="utf-8")
    for section in ("[LLM]", "[MCP]", "[TOOLS]", "[search]", "[SESSION]", "[UI]"):
        assert section in content
    assert "base_url" in content
    assert "sidebar_width" in content

    before = path.read_text(encoding="utf-8")
    _, created_again = ensure_config(path)
    assert created_again is False
    assert path.read_text(encoding="utf-8") == before


def test_config_uses_defaults_when_file_is_missing(tmp_path):
    cfg = Config(tmp_path / "missing.ini")

    assert cfg.base_url == "http://127.0.0.1:1234/v1"
    assert cfg.model == "your-model-name"
    assert cfg.llm_timeout == 120
    assert cfg.context_window == 0
    assert cfg.default_context_window == 128000
    assert cfg.mcp_connect_timeout == 30
    assert cfg.tool_timeout == 10
    assert cfg.session_dir == ".agents/sessions"
    assert cfg.session_auto_save is True
    assert cfg.sidebar_width == 34
    assert cfg.compact_threshold == 0.6


def test_config_reads_custom_values_and_falls_back(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text(
        """
[LLM]
base_url = http://localhost:8000/v1/
model = test-model
api_key = test-key
context_window = 4096
timeout = 33
compact_threshold = 0.8

[SESSION]
dir = .sessions
auto_save = false
list_limit = 5

[UI]
sidebar_width = 20
command_palette_max = 3
""".strip(),
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.base_url == "http://localhost:8000/v1"
    assert cfg.model == "test-model"
    assert cfg.context_window == 4096
    assert cfg.llm_timeout == 33
    assert cfg.compact_threshold == 0.8
    assert cfg.mcp_connect_timeout == 30
    assert cfg.session_dir == ".sessions"
    assert cfg.session_auto_save is False
    assert cfg.session_list_limit == 5
    assert cfg.sidebar_width == 20
    assert cfg.command_palette_max == 3


def test_config_invalid_number_uses_default(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text(
        "[LLM]\ntimeout = not-a-number\ncompact_threshold = nope\n",
        encoding="utf-8",
    )

    cfg = load_config(path)

    assert cfg.llm_timeout == 120
    assert cfg.compact_threshold == 0.6


def test_set_and_get_config_value(tmp_path):
    path = tmp_path / "config.ini"
    path.write_text(CONFIG_TEMPLATE, encoding="utf-8")

    set_config("LLM", "model", "new-model", path)
    set_config("CUSTOM", "key", "value", path)

    assert get_config_value("LLM", "model", path=path) == "new-model"
    assert get_config_value("CUSTOM", "key", path=path) == "value"
    assert load_config(path).model == "new-model"
