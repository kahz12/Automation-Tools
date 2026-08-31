import json
import os

from automation_tools.core import config


def test_get_env_var(monkeypatch):
    monkeypatch.setenv("AT_TEST_KEY", "value123")
    assert config.get_env_var("AT_TEST_KEY") == "value123"
    assert config.get_env_var("AT_MISSING_KEY") is None
    assert config.get_env_var("AT_MISSING_KEY", "fallback") == "fallback"


def test_get_project_root_points_to_repo():
    root = config.get_project_root()
    # The project root must contain the package source tree.
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


# ── where state and config live ─────────────────────────────────────────────
# The project used to write its database, its history and its log next to the
# source. That only works from a checkout: installed with pip the same path
# lands inside the interpreter's lib directory.

def test_user_data_dir_is_outside_the_source_tree(monkeypatch, tmp_path):
    # Every platform keeps this somewhere different, so pin all the inputs.
    monkeypatch.setenv("XDG_DATA_HOME", str(tmp_path))
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setattr(os.path, "expanduser", lambda p: str(tmp_path))

    path = config.user_data_dir()
    assert os.path.isdir(path)
    assert os.path.basename(path) == config.APP_DIRNAME
    assert str(tmp_path) in path
    assert "site-packages" not in path


def test_state_path_moves_a_checkout_file_once(monkeypatch, tmp_path, data_dir):
    root = tmp_path / "checkout"
    (root / "src" / "automation_tools").mkdir(parents=True)
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    (root / "history.json").write_text("mis datos", encoding="utf-8")

    monkeypatch.setattr(config, "get_project_root", lambda: str(root))

    moved = config.state_path("history.json")
    assert moved.startswith(str(data_dir))
    # The data came with it, and the old copy is gone rather than duplicated.
    assert open(moved, encoding="utf-8").read() == "mis datos"
    assert not (root / "history.json").exists()
    # Second call is a no-op.
    assert config.state_path("history.json") == moved


def test_state_path_never_overwrites_what_is_already_there(monkeypatch, tmp_path, data_dir):
    root = tmp_path / "checkout"
    (root / "src" / "automation_tools").mkdir(parents=True)
    (root / "pyproject.toml").write_text("", encoding="utf-8")
    (root / "history.json").write_text("vieja", encoding="utf-8")

    (data_dir / "history.json").write_text("actual", encoding="utf-8")

    monkeypatch.setattr(config, "get_project_root", lambda: str(root))

    assert open(config.state_path("history.json"), encoding="utf-8").read() == "actual"


def test_an_installed_copy_never_migrates_anything(monkeypatch, tmp_path, data_dir):
    """Installed, `get_project_root` points into lib/; files there are not ours."""
    fake_lib = tmp_path / "lib" / "python3.13"
    fake_lib.mkdir(parents=True)
    (fake_lib / "history.json").write_text("de otro", encoding="utf-8")

    monkeypatch.setattr(config, "get_project_root", lambda: str(fake_lib))

    path = config.state_path("history.json")
    assert path.startswith(str(data_dir))
    assert (fake_lib / "history.json").read_text(encoding="utf-8") == "de otro"


def test_config_is_looked_for_in_the_working_directory_first(monkeypatch, tmp_path, data_dir):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "cfg.json").write_text(
        json.dumps({"settings": {"currency_code": "EUR"}}), encoding="utf-8")
    assert config.load_json_config("cfg.json")["settings"]["currency_code"] == "EUR"


def test_config_is_also_found_in_the_data_directory(monkeypatch, tmp_path, data_dir):
    monkeypatch.chdir(tmp_path)
    (data_dir / "cfg.json").write_text(
        json.dumps({"settings": {"currency_code": "GBP"}}), encoding="utf-8")
    assert config.load_json_config("cfg.json")["settings"]["currency_code"] == "GBP"
