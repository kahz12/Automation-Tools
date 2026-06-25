import json

from automation_tools.core import config


def test_get_env_var(monkeypatch):
    monkeypatch.setenv("AT_TEST_KEY", "value123")
    assert config.get_env_var("AT_TEST_KEY") == "value123"
    assert config.get_env_var("AT_MISSING_KEY") is None
    assert config.get_env_var("AT_MISSING_KEY", "fallback") == "fallback"


def test_get_project_root_points_to_repo():
    root = config.get_project_root()
    # The project root must contain the package source tree.
    import os
    assert os.path.isdir(os.path.join(root, "src", "automation_tools"))


def test_get_downloads_folder_returns_str():
    assert isinstance(config.get_downloads_folder(), str)


def test_load_json_config_missing_returns_defaults(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_project_root", lambda: str(tmp_path))
    data = config.load_json_config("does_not_exist.json")
    assert data["products"] == []
    assert "telegram_token" in data["settings"]


def test_load_json_config_merges_settings(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_project_root", lambda: str(tmp_path))
    payload = {"settings": {"currency_code": "EUR"}, "products": [{"name": "x"}]}
    (tmp_path / "cfg.json").write_text(json.dumps(payload), encoding="utf-8")
    data = config.load_json_config("cfg.json")
    assert data["settings"]["currency_code"] == "EUR"
    # Defaults are filled in for keys the file omitted.
    assert data["settings"]["telegram_token"] == ""
    assert data["products"][0]["name"] == "x"


def test_load_json_config_accepts_bare_list(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "get_project_root", lambda: str(tmp_path))
    (tmp_path / "list.json").write_text(json.dumps([{"name": "a"}]), encoding="utf-8")
    data = config.load_json_config("list.json")
    assert data["products"] == [{"name": "a"}]
    assert "settings" in data
