"""Instagram downloader: URL routing, both engines, and the command line.

Nothing here touches the network. yt-dlp is replaced by a fake module that
hands back canned post metadata, and gallery-dl by a fake process that prints
canned output lines.
"""
import io
import sys
import threading
import types

import pytest

from automation_tools.tools import instagram_downloader as ig


def _out(capsys):
    """Captured output with Rich's line wrapping undone."""
    return " ".join(capsys.readouterr().out.split())


# ── URL routing ────────────────────────────────────────────────────────────
@pytest.mark.parametrize("target, kind, url", [
    ("https://www.instagram.com/p/ABC123/", "post", "https://www.instagram.com/p/ABC123/"),
    ("https://www.instagram.com/reel/AB-c_1/?igsh=zz", "post",
     "https://www.instagram.com/reel/AB-c_1/?igsh=zz"),
    ("instagram.com/reels/ABC/", "post", "https://instagram.com/reels/ABC/"),
    ("https://www.instagram.com/tv/XYZ/", "post", "https://www.instagram.com/tv/XYZ/"),
    ("https://www.instagram.com/some.one/p/ABC/", "post",
     "https://www.instagram.com/some.one/p/ABC/"),
    ("https://m.instagram.com/p/ABC/", "post", "https://m.instagram.com/p/ABC/"),
    ("https://www.instagram.com/someone/", "collection", "https://www.instagram.com/someone/"),
    ("https://www.instagram.com/someone/reels/", "collection",
     "https://www.instagram.com/someone/reels/"),
    ("https://www.instagram.com/stories/someone/", "collection",
     "https://www.instagram.com/stories/someone/"),
    # A share link only redirects to the post; gallery-dl follows it, yt-dlp does not.
    ("https://www.instagram.com/share/p/BAxyz/", "collection",
     "https://www.instagram.com/share/p/BAxyz/"),
    ("https://www.instagram.com/reels/audio/123/", "collection",
     "https://www.instagram.com/reels/audio/123/"),
    ("@some.one_", "collection", "https://www.instagram.com/some.one_/"),
    ("  someone  ", "collection", "https://www.instagram.com/someone/"),
])
def test_classify_url_routes_each_link_to_its_engine(target, kind, url):
    assert ig.classify_url(target) == (kind, url)


@pytest.mark.parametrize("target", [
    "https://youtube.com/watch?v=x",
    "https://notinstagram.com/p/ABC/",
    "https://instagram.com.evil.example/p/ABC/",
    "not a username!",
])
def test_classify_url_rejects_what_is_not_instagram(target):
    assert ig.classify_url(target)[0] == ""


def test_needs_login_flags_stories_highlights_and_share_links():
    assert ig.needs_login("https://www.instagram.com/stories/someone/")
    assert ig.needs_login("https://www.instagram.com/someone/highlights/")
    assert ig.needs_login("https://www.instagram.com/stories/highlights/1789/")
    assert ig.needs_login("https://www.instagram.com/share/p/BAxyz/")
    assert not ig.needs_login("https://www.instagram.com/someone/")
    assert not ig.needs_login("https://www.instagram.com/p/ABC/")


@pytest.mark.parametrize("url, ext", [
    ("https://cdn.example/v/abc_n.jpg?stp=dst-jpg_e35", ".jpg"),
    ("https://cdn.example/v/abc_n.jpeg", ".jpg"),
    ("https://cdn.example/v/abc_n.webp?stp=dst-jpg_e35", ".jpg"),
    ("https://cdn.example/v/abc_n.webp", ".webp"),
    ("https://cdn.example/v/abc_n.heic", ".heic"),
    ("https://cdn.example/v/abc", ".jpg"),
])
def test_image_extension(url, ext):
    assert ig._image_extension(url) == ext


# ── Validation happens before anything is downloaded ──────────────────────
@pytest.fixture
def downloads(monkeypatch, tmp_path):
    monkeypatch.setattr(ig, "get_downloads_folder", lambda: str(tmp_path))
    return tmp_path


@pytest.mark.parametrize("kwargs, message", [
    ({"url": "@someone", "media": "gifs"}, "Unknown media type"),
    ({"url": "@someone", "limit": 0}, "positive number"),
    ({"url": "https://youtube.com/watch?v=x"}, "Not an Instagram link"),
    ({"url": "@someone", "browser": "netscape"}, "Cannot read cookies"),
    ({"url": "@someone", "cookies": "/definitely/missing/cookies.txt"}, "not found"),
])
def test_bad_input_fails_early(downloads, capsys, kwargs, message):
    assert ig.run_instagram_downloader(**kwargs) is False
    assert message in _out(capsys)
    assert not (downloads / "Instagram").exists()


# ── Engine 2: gallery-dl for profiles, stories and highlights ────────────
def test_gallery_dl_command_defaults():
    cmd = ig.build_gallery_dl_command("https://www.instagram.com/someone/", "all", "/out")
    assert cmd[:3] == [sys.executable, "-m", "gallery_dl"]
    assert cmd[cmd.index("--destination") + 1] == "/out"
    assert 'directory=["{username}"]' in cmd
    assert cmd[cmd.index("--filename") + 1] == "{post_shortcode}_{num}.{extension}"
    assert cmd[-1] == "https://www.instagram.com/someone/"
    for flag in ("--filter", "--cookies", "--cookies-from-browser"):
        assert flag not in cmd
    assert not any(part.startswith(("videos=", "max-posts=")) for part in cmd)


def test_gallery_dl_command_options():
    images = ig.build_gallery_dl_command("u", "images", "/out", limit=5,
                                         cookie_file="/c.txt", browser="firefox")
    assert "videos=false" in images
    assert "max-posts=5" in images
    assert images[images.index("--cookies") + 1] == "/c.txt"
    assert images[images.index("--cookies-from-browser") + 1] == "firefox"

    videos = ig.build_gallery_dl_command("u", "videos", "/out")
    assert videos[videos.index("--filter") + 1] == "video_url"
    assert "videos=false" not in videos


class _FakeProcess:
    """Stands in for the gallery-dl process: canned output, canned exit code."""

    def __init__(self, lines, code):
        self.stdout = io.StringIO("".join(line + "\n" for line in lines))
        self._code = code
        self.terminated = False

    def wait(self, timeout=None):
        return self._code

    def terminate(self):
        self.terminated = True

    def kill(self):
        pass


@pytest.fixture
def fake_gallery_dl(monkeypatch):
    """Returns a function that queues the output of the next gallery-dl run."""
    state = {}

    def _popen(cmd, **kwargs):
        state["cmd"] = cmd
        state["kwargs"] = kwargs
        state["process"] = _FakeProcess(state["lines"], state["code"])
        return state["process"]

    monkeypatch.setattr(ig.subprocess, "Popen", _popen)
    monkeypatch.setattr(ig, "_gallery_dl_available", lambda: True)

    def _queue(lines, code=0):
        state["lines"], state["code"] = lines, code
        return state

    return _queue


def _saved_file(folder, name):
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    path.write_bytes(b"x")
    return str(path)


def test_profile_download_reports_saved_and_skipped(downloads, fake_gallery_dl, capsys):
    folder = downloads / "Instagram" / "someone"
    new = _saved_file(folder, "AAA_1.jpg")
    old = _saved_file(folder, "BBB_1.mp4")
    state = fake_gallery_dl([new, "# " + old], code=0)

    assert ig.run_instagram_downloader("@someone", limit=2) is True

    out = _out(capsys)
    assert "AAA_1.jpg" in out and "BBB_1.mp4 is already there" in out
    assert "1 file(s) saved" in out
    assert "max-posts=2" in state["cmd"]
    # The child must never read from, or wait on, the terminal.
    assert state["kwargs"]["stdin"] is ig.subprocess.DEVNULL


def test_recovered_lookup_exit_code_is_still_a_success(downloads, fake_gallery_dl, capsys):
    """gallery-dl exits 4 after retrying a failed user search that it recovered from."""
    new = _saved_file(downloads / "Instagram" / "someone", "AAA_1.jpg")
    fake_gallery_dl([new], code=4)
    assert ig.run_instagram_downloader("@someone") is True


def test_logged_errors_fail_the_run_and_suggest_cookies(downloads, fake_gallery_dl, capsys):
    fake_gallery_dl([
        "[instagram][error] HTTP redirect to login page "
        "(https://www.instagram.com/accounts/login/)",
    ], code=4)
    assert ig.run_instagram_downloader("https://www.instagram.com/someone/") is False
    out = _out(capsys)
    assert "HTTP redirect to login page" in out
    assert "cookies.txt" in out


def test_empty_stories_without_login_explain_the_login(downloads, fake_gallery_dl, capsys):
    fake_gallery_dl(["[instagram][info] No results for "
                     "https://www.instagram.com/stories/someone/"], code=4)
    assert ig.run_instagram_downloader("https://www.instagram.com/stories/someone/") is False
    out = _out(capsys)
    assert "usually need a login" in out
    assert "returned nothing" in out
    assert "cookies.txt" in out


def test_empty_result_with_login_points_at_the_session(downloads, fake_gallery_dl, capsys,
                                                       tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    state = fake_gallery_dl([], code=4)
    assert ig.run_instagram_downloader("@private.one", cookies=str(cookies)) is False
    out = _out(capsys)
    assert "follows it" in out
    assert state["cmd"][state["cmd"].index("--cookies") + 1] == str(cookies)


def test_a_clean_run_with_nothing_to_fetch_is_not_an_error(downloads, fake_gallery_dl, capsys):
    fake_gallery_dl([], code=0)
    assert ig.run_instagram_downloader("@someone", media="videos") is True
    assert "Nothing to download" in _out(capsys)


def test_cancelling_stops_gallery_dl(downloads, fake_gallery_dl, capsys):
    state = fake_gallery_dl(["[instagram][info] working"], code=0)
    cancel = threading.Event()
    cancel.set()
    assert ig.run_instagram_downloader("@someone", cancel_event=cancel) is False
    assert state["process"].terminated
    assert "Cancelled" in _out(capsys)


def test_missing_gallery_dl_is_reported(downloads, monkeypatch, capsys):
    monkeypatch.setattr(ig, "_gallery_dl_available", lambda: False)
    assert ig.run_instagram_downloader("@someone") is False
    assert "pip install gallery-dl" in _out(capsys)


# ── Engine 1: yt-dlp for single posts ─────────────────────────────────────
class _DownloadError(Exception):
    pass


class _FakeYoutubeDL:
    """Enough of yt_dlp.YoutubeDL for the single-post engine."""

    info = None
    instances = []
    fail_urls = set()
    extract_error = None

    def __init__(self, params):
        self.params = params
        self.processed = []
        _FakeYoutubeDL.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        if self.extract_error is not None:
            raise self.extract_error
        return self.info

    def urlopen(self, url):
        if url in self.fail_urls:
            raise OSError("connection reset")
        return io.BytesIO(b"image from " + url.encode())

    @staticmethod
    def sanitize_info(info, remove_private_keys=False):
        return dict(info)

    def process_ie_result(self, entry, download=True):
        self.processed.append(entry)
        target = self.params["outtmpl"]["default"] % {"ext": "mp4"}
        with open(target, "wb") as handle:
            handle.write(b"video " + entry["id"].encode())


@pytest.fixture
def fake_ytdlp(monkeypatch):
    utils = types.SimpleNamespace(
        DownloadError=_DownloadError,
        DownloadCancelled=type("DownloadCancelled", (Exception,), {}),
        YoutubeDLError=type("YoutubeDLError", (Exception,), {}),
    )
    module = types.SimpleNamespace(YoutubeDL=_FakeYoutubeDL, utils=utils)
    monkeypatch.setitem(sys.modules, "yt_dlp", module)
    _FakeYoutubeDL.instances = []
    _FakeYoutubeDL.fail_urls = set()
    _FakeYoutubeDL.extract_error = None
    return _FakeYoutubeDL


def _photo(code, url):
    return {"id": code, "channel": "someone", "formats": [], "thumbnail": url}


def _video(code):
    return {"id": code, "channel": "someone", "formats": [{"format_id": "dash"}]}


CAROUSEL = {
    "_type": "playlist", "id": "POST1",
    "entries": [
        _photo("c1", "https://cdn.example/one_n.jpg?stp=dst-jpg"),
        _video("c2"),
        _photo("c3", "https://cdn.example/three_n.webp?stp=dst-jpg"),
    ],
}


def test_carousel_saves_photos_and_videos_in_order(downloads, fake_ytdlp, capsys):
    fake_ytdlp.info = CAROUSEL
    progress = []

    ok = ig.run_instagram_downloader(
        "https://www.instagram.com/p/POST1/",
        progress_callback=lambda **kw: progress.append(kw))

    assert ok is True
    folder = downloads / "Instagram" / "someone"
    assert sorted(p.name for p in folder.iterdir()) == ["POST1_1.jpg", "POST1_2.mp4", "POST1_3.jpg"]
    assert (folder / "POST1_1.jpg").read_bytes() == b"image from https://cdn.example/one_n.jpg?stp=dst-jpg"
    assert (folder / "POST1_2.mp4").read_bytes() == b"video c2"
    assert "carousel of 3" in _out(capsys)
    assert progress[-1] == {"current": 3, "total": 3, "message": "Done"}
    # Photos need yt-dlp to carry on past "no video formats".
    assert fake_ytdlp.instances[0].params["ignore_no_formats_error"] is True


@pytest.mark.parametrize("media, expected", [
    ("images", ["POST1_1.jpg", "POST1_3.jpg"]),
    ("videos", ["POST1_2.mp4"]),
])
def test_media_filter_keeps_carousel_numbering(downloads, fake_ytdlp, media, expected):
    fake_ytdlp.info = CAROUSEL
    assert ig.run_instagram_downloader("https://www.instagram.com/p/POST1/", media=media)
    folder = downloads / "Instagram" / "someone"
    assert sorted(p.name for p in folder.iterdir()) == expected


def test_single_photo_post(downloads, fake_ytdlp):
    fake_ytdlp.info = _photo("SOLO", "https://cdn.example/solo_n.jpg")
    assert ig.run_instagram_downloader("https://www.instagram.com/reel/SOLO/")
    assert (downloads / "Instagram" / "someone" / "SOLO_1.jpg").exists()


def test_videos_only_on_a_photo_post_is_a_warning_not_a_failure(downloads, fake_ytdlp, capsys):
    fake_ytdlp.info = _photo("SOLO", "https://cdn.example/solo_n.jpg")
    assert ig.run_instagram_downloader("https://www.instagram.com/p/SOLO/", media="videos") is True
    assert "no videos" in _out(capsys)
    assert not (downloads / "Instagram" / "someone").exists()


def test_files_already_there_are_not_downloaded_again(downloads, fake_ytdlp, capsys):
    fake_ytdlp.info = CAROUSEL
    folder = downloads / "Instagram" / "someone"
    folder.mkdir(parents=True)
    (folder / "POST1_1.jpg").write_bytes(b"mine")
    (folder / "POST1_2.mp4").write_bytes(b"mine too")

    assert ig.run_instagram_downloader("https://www.instagram.com/p/POST1/")

    assert (folder / "POST1_1.jpg").read_bytes() == b"mine"
    assert (folder / "POST1_2.mp4").read_bytes() == b"mine too"
    assert (folder / "POST1_3.jpg").exists()
    out = _out(capsys)
    assert "POST1_1.jpg is already there" in out
    assert "2 file(s) were already downloaded" in out
    # No second yt-dlp was built for the video that was already on disk.
    assert len(fake_ytdlp.instances) == 1


def test_one_broken_item_does_not_stop_the_rest(downloads, fake_ytdlp, capsys):
    fake_ytdlp.info = CAROUSEL
    fake_ytdlp.fail_urls = {"https://cdn.example/one_n.jpg?stp=dst-jpg"}

    assert ig.run_instagram_downloader("https://www.instagram.com/p/POST1/") is False

    folder = downloads / "Instagram" / "someone"
    assert sorted(p.name for p in folder.iterdir()) == ["POST1_2.mp4", "POST1_3.jpg"]
    out = _out(capsys)
    assert "connection reset" in out
    assert "1 item(s) could not be downloaded" in out


def test_cookies_reach_yt_dlp(downloads, fake_ytdlp, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    fake_ytdlp.info = _photo("SOLO", "https://cdn.example/solo_n.jpg")
    assert ig.run_instagram_downloader("https://www.instagram.com/p/SOLO/", cookies=str(cookies))
    assert fake_ytdlp.instances[0].params["cookiefile"] == str(cookies)


def test_login_wall_on_a_post_suggests_cookies(downloads, fake_ytdlp, capsys):
    fake_ytdlp.extract_error = _DownloadError(
        "[Instagram] X: Requested content is not available, rate-limit reached "
        "or login required. Use --cookies")
    assert ig.run_instagram_downloader("https://www.instagram.com/p/X/") is False
    assert "cookies.txt" in _out(capsys)


def test_cancel_before_the_first_item_writes_nothing(downloads, fake_ytdlp):
    fake_ytdlp.info = CAROUSEL
    cancel = threading.Event()
    cancel.set()
    assert ig.run_instagram_downloader("https://www.instagram.com/p/POST1/",
                                       cancel_event=cancel) is False
    assert not (downloads / "Instagram" / "someone").exists()


def test_save_image_cleans_up_when_cancelled_mid_file(tmp_path):
    cancel = threading.Event()

    class _Response(io.BytesIO):
        def read(self, size=-1):
            cancel.set()  # the user presses cancel while bytes are arriving
            return super().read(size)

    ydl = types.SimpleNamespace(urlopen=lambda url: _Response(b"x" * 200_000))
    base = str(tmp_path / "someone" / "POST_1")
    with pytest.raises(ig._Cancelled):
        ig._save_image(ydl, {"thumbnail": "https://cdn.example/a.jpg"}, base, cancel)
    assert list((tmp_path / "someone").iterdir()) == []


# ── Command line ───────────────────────────────────────────────────────────
@pytest.fixture
def cli(monkeypatch):
    seen = {}

    def _run(url, **kwargs):
        seen["url"] = url
        seen.update(kwargs)
        return True

    monkeypatch.setattr(ig, "run_instagram_downloader", _run)
    monkeypatch.setattr(ig, "load_environment", lambda: None)
    monkeypatch.delenv(ig.COOKIES_ENV, raising=False)

    def _main(*argv):
        monkeypatch.setattr(sys, "argv", ["instagram_downloader", *argv])
        with pytest.raises(SystemExit) as excinfo:
            ig.main()
        return excinfo.value.code

    return _main, seen


def test_cli_forwards_every_option(cli):
    main, seen = cli
    assert main("@someone", "--media", "images", "--limit", "3",
                "--cookies", "c.txt", "--out-dir", "out") == 0
    assert seen == {"url": "@someone", "media": "images", "limit": 3, "cookies": "c.txt",
                    "browser": None, "output_dir": "out"}


def test_cli_accepts_spanish_aliases(cli):
    main, seen = cli
    assert main("@someone", "--contenido", "videos", "--limite", "5",
                "--navegador", "Firefox") == 0
    assert (seen["media"], seen["limit"], seen["browser"]) == ("videos", 5, "firefox")


def test_cli_reads_the_cookies_file_from_the_environment(cli, monkeypatch):
    main, seen = cli
    monkeypatch.setenv(ig.COOKIES_ENV, "/home/me/ig_cookies.txt")
    main("@someone")
    assert seen["cookies"] == "/home/me/ig_cookies.txt"


def test_cli_browser_wins_over_the_environment_cookies(cli, monkeypatch):
    main, seen = cli
    monkeypatch.setenv(ig.COOKIES_ENV, "/home/me/ig_cookies.txt")
    main("@someone", "--browser", "chrome")
    assert seen["cookies"] is None and seen["browser"] == "chrome"


def test_cli_rejects_a_non_positive_limit(cli):
    main, _seen = cli
    assert main("@someone", "--limit", "0") == 2


def test_cli_failure_becomes_exit_code_1(cli, monkeypatch):
    main, _seen = cli
    monkeypatch.setattr(ig, "run_instagram_downloader", lambda url, **kw: False)
    assert main("@someone") == 1


# ── Dashboard screen ───────────────────────────────────────────────────────
def _drive_screen(monkeypatch, fill):
    """Mounts the screen, lets `fill` set its fields, presses RUN.

    Returns (kwargs the tool would have been run with or None, error text,
    initial cookies field value).
    """
    import asyncio

    from textual.app import App
    from textual.widgets import Static

    from automation_tools.cli.screens import InstagramScreen

    calls = []

    async def fake_run_tool(self, fn, **kwargs):
        calls.append((fn, kwargs))

    monkeypatch.setattr(InstagramScreen, "_run_tool", fake_run_tool)

    class _Harness(App):
        def on_mount(self):
            self.push_screen(InstagramScreen())

    async def go():
        app = _Harness()
        async with app.run_test() as pilot:
            await pilot.pause()
            screen = app.screen
            initial_cookies = screen.query_one("#cookies").value
            fill(screen)
            await pilot.pause()
            await screen.action_do_run()
            await pilot.pause()
            error = str(screen.query_one("#error-msg", Static).render())
            return initial_cookies, error

    initial_cookies, error = asyncio.run(go())
    if calls:
        fn, kwargs = calls[0]
        assert fn is ig.run_instagram_downloader
        return kwargs, error, initial_cookies
    return None, error, initial_cookies


def test_screen_runs_the_tool_with_the_form_values(monkeypatch, tmp_path):
    cookies = tmp_path / "cookies.txt"
    cookies.write_text("# Netscape HTTP Cookie File\n")
    monkeypatch.delenv(ig.COOKIES_ENV, raising=False)

    def fill(screen):
        screen.query_one("#url").value = "@someone"
        screen.query_one("#rb-images").value = True
        screen.query_one("#limit").value = "5"
        screen.query_one("#cookies").value = str(cookies)

    kwargs, error, _ = _drive_screen(monkeypatch, fill)
    assert error == ""
    assert kwargs == {"url": "@someone", "media": "images", "limit": 5,
                      "cookies": str(cookies)}


def test_screen_prefills_cookies_from_the_environment(monkeypatch):
    monkeypatch.setenv(ig.COOKIES_ENV, "/home/me/ig_cookies.txt")
    _kwargs, _error, initial = _drive_screen(monkeypatch, lambda screen: None)
    assert initial == "/home/me/ig_cookies.txt"


@pytest.mark.parametrize("url, limit, cookies, message", [
    ("", "", "", "is required"),
    ("https://youtube.com/watch?v=x", "", "", "not an Instagram link"),
    ("@someone", "0", "", "1 or more"),
    ("@someone", "", "/definitely/missing.txt", "Cookies file not found"),
])
def test_screen_rejects_bad_input_without_running(monkeypatch, url, limit, cookies, message):
    monkeypatch.delenv(ig.COOKIES_ENV, raising=False)

    def fill(screen):
        screen.query_one("#url").value = url
        screen.query_one("#limit").value = limit
        screen.query_one("#cookies").value = cookies

    kwargs, error, _ = _drive_screen(monkeypatch, fill)
    assert kwargs is None
    assert message in error
