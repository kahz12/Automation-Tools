from automation_tools.tools import youtube_downloader as yt


def test_is_playlist():
    assert yt._is_playlist("https://www.youtube.com/playlist?list=PLxyz") is True
    assert yt._is_playlist("https://youtube.com/watch?v=abc&list=PLxyz") is True
    assert yt._is_playlist("https://youtu.be/abc") is False


def _capture(monkeypatch, tmp_path):
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return None

    monkeypatch.setattr(yt, "get_downloads_folder", lambda: str(tmp_path))
    monkeypatch.setattr(yt.subprocess, "run", fake_run)
    return captured


def test_audio_command(monkeypatch, tmp_path):
    captured = _capture(monkeypatch, tmp_path)
    yt.run_youtube_downloader("https://youtu.be/abc", mode="audio", resume=False)
    cmd = captured["cmd"]
    assert "-x" in cmd
    assert "mp3" in cmd
    assert cmd[-1] == "https://youtu.be/abc"


def test_video_command_uses_no_playlist(monkeypatch, tmp_path):
    captured = _capture(monkeypatch, tmp_path)
    yt.run_youtube_downloader("https://youtu.be/abc", mode="video", resume=False)
    cmd = captured["cmd"]
    assert "--no-playlist" in cmd
    assert "-f" in cmd
