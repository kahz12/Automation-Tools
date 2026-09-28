"""Download photos and videos from Instagram: posts, reels, carousels,
profiles, stories and highlights.

Neither of the usual downloaders covers all of that on its own, so this uses
two, each where it works (checked against Instagram in September 2026):

* A link to one post, reel or IGTV video goes through yt-dlp, which the
  project already depends on and which reads public posts without a login.
  yt-dlp only downloads videos, but for every photo it reports the original,
  full-size JPEG as the entry's best thumbnail, so photos are fetched from
  there. gallery-dl cannot do this part anonymously: it asks Instagram's
  per-post API, which redirects to the login page.
* Anything else on instagram.com (a profile, its reels or tagged tabs,
  stories, highlights, share links) goes through gallery-dl. yt-dlp's profile
  extractor is marked broken, while gallery-dl lists public profiles without
  a login. Stories and highlights need a session whichever tool asks.

Both engines save to ``<out-dir>/<username>/<post shortcode>_<n>.<ext>``, so a
post fetched by its link is recognised and skipped when its profile is
downloaded later, and the other way round.
"""
from __future__ import annotations

import argparse
import importlib.util
import os
import queue
import re
import subprocess
import sys
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
from urllib.parse import urlparse

from rich.markup import escape

from automation_tools.core.cli import ArgumentParser, exit_code
from automation_tools.core.config import get_downloads_folder, get_env_var, load_environment
from automation_tools.core.logger import (
    console, print_error, print_step, print_success, print_warning,
)

MEDIA_CHOICES = ("all", "images", "videos")
COOKIES_ENV = "INSTAGRAM_COOKIES"

_MEDIA_LABELS = {"all": "photos and videos", "images": "photos only", "videos": "videos only"}

_HOST = r"(?:https?://)?(?:www\.|m\.)?instagram\.com"
# /p/<code>, /reel/<code>, /reels/<code> and /tv/<code>, optionally behind a
# username, which is how the web app links to posts now. /reels/audio/<id> is
# a sound page, not a post, and /share/... links only redirect to one, which
# yt-dlp does not follow, so both go to gallery-dl.
_POST_RE = re.compile(
    _HOST + r"/(?:(?!share/)[\w.]+/)?(?:p|reels?|tv)/(?!audio/)([\w-]+)",
    re.IGNORECASE)
_INSTAGRAM_RE = re.compile(_HOST + r"(?:[/?#]|$)", re.IGNORECASE)
# Instagram usernames are letters, digits, dots and underscores, at most 30.
_USERNAME_RE = re.compile(r"@?([A-Za-z0-9._]{1,30})")
# Paths that only a logged-in session can read, whichever engine asks.
_LOGIN_PATHS = ("/stories/", "/highlights", "/saved", "/explore/tags/", "/share/")

# The browsers yt-dlp and gallery-dl can both read cookies from.
BROWSERS = ("brave", "chrome", "chromium", "edge", "firefox", "opera",
            "safari", "vivaldi")

_IMAGE_EXTS = (".jpg", ".jpeg", ".png", ".webp", ".heic")
_VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".mov")

_LOGIN_HINT = (
    "Instagram only shows this to a logged-in account. Export your "
    "instagram.com cookies to a cookies.txt file (Netscape format, any "
    "\"cookies.txt\" browser extension does it) and pass it with --cookies "
    "FILE, or set INSTAGRAM_COOKIES in .env. On a computer, --browser firefox "
    "reads them straight from the browser instead."
)

_SESSION_HINT = (
    "If the account is private, the cookies must come from an account that "
    "follows it. Cookies also expire: export them again if this used to work."
)


class _Cancelled(Exception):
    """The run was cancelled between two safe steps."""


# ── URL handling ───────────────────────────────────────────────────────────
def classify_url(target: str) -> Tuple[str, str]:
    """Work out which engine a link or username belongs to.

    Returns ``(kind, url)``. ``kind`` is ``"post"`` for a single post, reel or
    video, ``"collection"`` for anything else on instagram.com (a bare
    ``user`` or ``@user`` becomes that profile), and ``""`` when the input is
    not Instagram at all.
    """
    text = target.strip()
    if _POST_RE.match(text):
        return "post", _with_scheme(text)
    if _INSTAGRAM_RE.match(text):
        return "collection", _with_scheme(text)
    match = _USERNAME_RE.fullmatch(text)
    if match:
        return "collection", f"https://www.instagram.com/{match.group(1)}/"
    return "", text


def _with_scheme(url: str) -> str:
    return url if re.match(r"https?://", url, re.IGNORECASE) else "https://" + url


def needs_login(url: str) -> bool:
    """Whether Instagram only serves this page to a logged-in account."""
    path = urlparse(_with_scheme(url)).path.lower()
    return any(part in path for part in _LOGIN_PATHS)


def _safe_name(name: str) -> str:
    """A path component from an Instagram name, which is ASCII already."""
    cleaned = re.sub(r"[^\w.-]", "_", name).strip()
    return cleaned if cleaned.strip(".") else "_"


# ── Engine 1: single posts through yt-dlp ─────────────────────────────────
class _YtdlpLogger:
    """Keeps yt-dlp's chatter out of the console and passes on what matters.

    With a logger set, yt-dlp sends every screen message to ``debug``. The
    warnings below appear for every photo, because yt-dlp is looking for a
    video in it, so repeating them would only alarm.
    """

    _EXPECTED = (
        "No video formats found",
        "Requested format is not available",
        "There is no video in this post",
    )

    def debug(self, msg: str) -> None:
        pass

    def info(self, msg: str) -> None:
        pass

    def warning(self, msg: str) -> None:
        if not any(expected in msg for expected in self._EXPECTED):
            print_warning(escape(msg))

    def error(self, msg: str) -> None:
        print_error(escape(re.sub(r"^ERROR:\s*", "", msg)))


def _ytdlp_params(cookie_file: Optional[str], browser: Optional[str]) -> Dict[str, Any]:
    params: Dict[str, Any] = {
        "quiet": True,
        "noprogress": True,
        "color": "no_color",
        "logger": _YtdlpLogger(),
        # A photo has no video formats. Without this, yt-dlp stops at the
        # first photo instead of reporting it with its full-size image.
        "ignore_no_formats_error": True,
        "merge_output_format": "mp4",
    }
    if cookie_file:
        params["cookiefile"] = cookie_file
    if browser:
        params["cookiesfrombrowser"] = (browser,)
    return params


def _best_image_url(entry: Dict[str, Any]) -> Optional[str]:
    """The full-size photo: yt-dlp sorts thumbnails so the best one is last."""
    if entry.get("thumbnail"):
        return entry["thumbnail"]
    for thumb in reversed(entry.get("thumbnails") or []):
        if thumb.get("url"):
            return thumb["url"]
    return None


def _image_extension(url: str) -> str:
    ext = os.path.splitext(urlparse(url).path)[1].lower()
    if ext == ".jpeg" or (ext == ".webp" and "stp=dst-jpg" in url):
        return ".jpg"
    return ext if ext in _IMAGE_EXTS else ".jpg"


def _existing(base: str, extensions: Tuple[str, ...]) -> Optional[str]:
    for ext in extensions:
        if os.path.isfile(base + ext):
            return base + ext
    return None


def _save_image(ydl: Any, entry: Dict[str, Any], base: str,
                cancel_event: Optional[threading.Event]) -> Tuple[str, bool]:
    """Download one photo. Returns its path and whether it is new."""
    existing = _existing(base, _IMAGE_EXTS)
    if existing:
        return existing, False
    url = _best_image_url(entry)
    if not url:
        raise ValueError("Instagram returned no image for this item")
    target = base + _image_extension(url)

    os.makedirs(os.path.dirname(target), exist_ok=True)
    partial = target + ".part"
    try:
        with ydl.urlopen(url) as response, open(partial, "wb") as handle:
            while True:
                if cancel_event is not None and cancel_event.is_set():
                    raise _Cancelled()
                chunk = response.read(1 << 16)
                if not chunk:
                    break
                handle.write(chunk)
        os.replace(partial, target)
    finally:
        if os.path.exists(partial):
            os.remove(partial)
    return target, True


def _save_video(params: Dict[str, Any], entry: Dict[str, Any], base: str,
                cancel_event: Optional[threading.Event]) -> Tuple[str, bool]:
    """Download one video. Returns its path and whether it is new."""
    existing = _existing(base, _VIDEO_EXTS)
    if existing:
        return existing, False
    import yt_dlp

    def _hook(_status: Dict[str, Any]) -> None:
        if cancel_event is not None and cancel_event.is_set():
            raise _Cancelled()

    options = dict(params)
    # "%" starts a field in yt-dlp templates, and a folder name may contain one.
    options["outtmpl"] = {"default": base.replace("%", "%%") + ".%(ext)s"}
    options["progress_hooks"] = [_hook]
    os.makedirs(os.path.dirname(base), exist_ok=True)
    with yt_dlp.YoutubeDL(options) as video_dl:
        # The entry was already extracted; this is what yt-dlp's own
        # --load-info-json does with one, so Instagram is not asked twice.
        video_dl.process_ie_result(
            yt_dlp.YoutubeDL.sanitize_info(entry, remove_private_keys=True),
            download=True)
    return _existing(base, _VIDEO_EXTS) or base + ".mp4", True


def _post_details(info: Dict[str, Any], entries: List[Dict[str, Any]],
                  url: str) -> Tuple[str, str]:
    """The post's shortcode and its author's username, as gallery-dl names them."""
    shortcode = info.get("id")
    if not shortcode:
        match = _POST_RE.match(url)
        shortcode = match.group(1) if match else "post"
    username = info.get("channel") or next(
        (e.get("channel") for e in entries if e.get("channel")), None)
    return _safe_name(str(shortcode)), _safe_name(str(username or "unknown"))


def _download_post(url: str, media: str, out_root: str,
                   cookie_file: Optional[str], browser: Optional[str],
                   cancel_event: Optional[threading.Event],
                   progress_callback: Optional[Callable[..., None]]) -> bool:
    try:
        import yt_dlp
    except ImportError:
        print_error("yt-dlp is not installed. Run: pip install yt-dlp")
        return False

    params = _ytdlp_params(cookie_file, browser)
    print_step("Reading the post…")
    with yt_dlp.YoutubeDL(params) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
        except yt_dlp.utils.DownloadError as exc:
            # The logger already printed yt-dlp's own message.
            if "login" in str(exc).lower() or "cookies" in str(exc).lower():
                console.print(f"[dim]💡 {escape(_LOGIN_HINT)}[/dim]")
            return False
        except (yt_dlp.utils.YoutubeDLError, OSError, ValueError) as exc:
            # A cookies file that is not in Netscape format, or a browser
            # profile that cannot be read, fails here rather than as a
            # download error.
            print_error(escape(str(exc)))
            return False
        if not info:
            print_error("Instagram returned nothing for that link.")
            return False

        if info.get("_type") == "playlist":
            entries = [e for e in (info.get("entries") or []) if e]
        else:
            entries = [info]
        shortcode, username = _post_details(info, entries, url)
        folder = os.path.join(out_root, username)

        # Numbered by position in the carousel, like gallery-dl, even when the
        # filter leaves some positions out.
        wanted = []
        for num, entry in enumerate(entries, 1):
            is_video = bool(entry.get("formats"))
            if (media == "images" and is_video) or (media == "videos" and not is_video):
                continue
            wanted.append((num, entry, is_video))

        if len(entries) > 1:
            shape = f"carousel of {len(entries)}"
        else:
            shape = "video" if entries and entries[0].get("formats") else "photo"
        print_step(f"@{escape(username)} · {shape}")
        if not wanted:
            print_warning(f"This post has no {'videos' if media == 'videos' else 'photos'}.")
            return True

        saved = skipped = failed = 0
        for index, (num, entry, is_video) in enumerate(wanted, 1):
            if cancel_event is not None and cancel_event.is_set():
                console.print("[dim #f59e0b]Cancelled before the next item.[/]")
                return False
            if progress_callback is not None:
                progress_callback(current=index - 1, total=len(wanted),
                                  message=f"Item {index}/{len(wanted)}")
            base = os.path.join(folder, f"{shortcode}_{num}")
            try:
                path, is_new = (_save_video(params, entry, base, cancel_event) if is_video
                                else _save_image(ydl, entry, base, cancel_event))
            except (_Cancelled, yt_dlp.utils.DownloadCancelled):
                console.print("[dim #f59e0b]Cancelled; the partial file was left out.[/]")
                return False
            except yt_dlp.utils.DownloadError:
                failed += 1  # the logger already printed yt-dlp's reason
                continue
            except Exception as exc:  # one broken item should not sink the rest
                failed += 1
                print_error(f"Item {num}: {escape(str(exc))}")
                continue
            if is_new:
                saved += 1
                console.print(f"[#22c55e]✓[/] {escape(os.path.basename(path))}")
            else:
                skipped += 1
                console.print(f"[dim]↷ {escape(os.path.basename(path))} is already there[/dim]")

        if progress_callback is not None:
            progress_callback(current=len(wanted), total=len(wanted), message="Done")
    _report(saved, skipped, folder)
    if failed:
        print_error(f"{failed} item(s) could not be downloaded.")
    return failed == 0


# ── Engine 2: profiles, stories and the rest through gallery-dl ───────────
def build_gallery_dl_command(url: str, media: str, out_root: str,
                             limit: Optional[int] = None,
                             cookie_file: Optional[str] = None,
                             browser: Optional[str] = None) -> List[str]:
    """The gallery-dl command line for a profile, stories or highlights link."""
    cmd = [
        sys.executable, "-m", "gallery_dl",
        "--destination", out_root,
        # One folder per account, named like the single-post engine names it.
        "--option", 'directory=["{username}"]',
        "--filename", "{post_shortcode}_{num}.{extension}",
    ]
    if media == "images":
        # Skips videos outright rather than downloading and discarding them.
        cmd += ["--option", "videos=false"]
    elif media == "videos":
        cmd += ["--filter", "video_url"]
    if limit:
        cmd += ["--option", f"max-posts={limit}"]
    if cookie_file:
        cmd += ["--cookies", cookie_file]
    if browser:
        cmd += ["--cookies-from-browser", browser]
    cmd.append(url)
    return cmd


def _gallery_dl_available() -> bool:
    return importlib.util.find_spec("gallery_dl") is not None


def _stop(process: "subprocess.Popen[str]") -> None:
    process.terminate()
    try:
        process.wait(timeout=5)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait()


def _download_collection(url: str, media: str, out_root: str, limit: Optional[int],
                         cookie_file: Optional[str], browser: Optional[str],
                         cancel_event: Optional[threading.Event],
                         progress_callback: Optional[Callable[..., None]]) -> bool:
    if not _gallery_dl_available():
        print_error("gallery-dl is not installed. Run: pip install gallery-dl")
        return False

    cmd = build_gallery_dl_command(url, media, out_root, limit, cookie_file, browser)
    print_step("Asking Instagram for the list… requests are paced a few "
               "seconds apart, so a large profile takes a while.")
    console.print(f"[cyan]{'-' * 50}[/cyan]")

    # Unbuffered so each file shows up as it lands; stdin closed so a prompt
    # can never wait on (or steal keys from) the terminal.
    env = dict(os.environ, PYTHONUNBUFFERED="1", PYTHONIOENCODING="utf-8")
    try:
        process = subprocess.Popen(
            cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL, env=env, text=True,
            encoding="utf-8", errors="replace")
    except OSError as exc:
        print_error(f"Could not start gallery-dl: {escape(str(exc))}")
        return False

    # Reading the pipe blocks, so a thread feeds a queue and this loop stays
    # free to notice a cancellation.
    lines: "queue.Queue[Optional[str]]" = queue.Queue()

    def _pump() -> None:
        try:
            assert process.stdout is not None
            for raw in process.stdout:
                lines.put(raw)
        finally:
            lines.put(None)

    threading.Thread(target=_pump, daemon=True).start()

    counts = {"saved": 0, "skipped": 0, "errors": 0}
    login_needed = False
    while True:
        if cancel_event is not None and cancel_event.is_set():
            _stop(process)
            console.print("[dim #f59e0b]Cancelled. Files already saved are kept.[/]")
            return False
        try:
            raw = lines.get(timeout=0.25)
        except queue.Empty:
            continue
        if raw is None:
            break
        line = raw.rstrip("\r\n")
        if not line.strip():
            continue
        login_needed |= _report_line(line, counts)
        if progress_callback is not None:
            progress_callback(message=f"{counts['saved']} saved · {counts['skipped']} already there")

    code = process.wait()
    console.print(f"[cyan]{'-' * 50}[/cyan]")
    # gallery-dl ORs a code into its exit status even for a lookup it retried
    # and recovered from (a failed user search, say), so a non-zero status
    # with files and no logged error is still a success.
    got_files = counts["saved"] + counts["skipped"] > 0
    ok = counts["errors"] == 0 and (code == 0 or got_files)
    _report(counts["saved"], counts["skipped"], out_root)
    if not ok and not counts["errors"]:
        # Typically "[instagram][info] No results": stories and private
        # accounts look empty from outside rather than raising an error.
        print_error(f"Instagram returned nothing for this link "
                    f"(gallery-dl exit code {code}).")
    if ok and not got_files:
        print_warning("Nothing to download: nothing matched, or Instagram hid it.")
    logged_in = bool(cookie_file or browser)
    if login_needed or code & 16 or (not ok and not logged_in):
        console.print(f"[dim]💡 {escape(_LOGIN_HINT)}[/dim]")
    elif not ok:
        console.print(f"[dim]💡 {escape(_SESSION_HINT)}[/dim]")
    return ok


def _report_line(line: str, counts: Dict[str, int]) -> bool:
    """Print one line of gallery-dl output. Returns True if it asks for a login."""
    lowered = line.lower()
    if line.startswith("# "):
        counts["skipped"] += 1
        console.print(f"[dim]↷ {escape(os.path.basename(line[2:]))} is already there[/dim]")
    elif "][error]" in lowered:
        counts["errors"] += 1
        print_error(escape(line.split("]", 2)[-1].strip() or line))
        return "login" in lowered or "cookies" in lowered
    elif "][warning]" in lowered:
        print_warning(escape(line.split("]", 2)[-1].strip() or line))
        return "login" in lowered
    elif os.path.isfile(line):
        counts["saved"] += 1
        console.print(f"[#22c55e]✓[/] {escape(os.path.basename(line))}")
    else:
        # Informational log lines, or a Python warning from the child.
        console.print(f"[dim]{escape(line)}[/dim]")
    return False


def _report(saved: int, skipped: int, folder: str) -> None:
    if saved:
        print_success(f"{saved} file(s) saved in [bold]{escape(folder)}[/bold]")
    if skipped:
        console.print(f"[dim]{skipped} file(s) were already downloaded and were skipped.[/dim]")


# ── Entry points ───────────────────────────────────────────────────────────
def run_instagram_downloader(
    url: str,
    media: str = "all",
    limit: Optional[int] = None,
    cookies: Optional[str] = None,
    browser: Optional[str] = None,
    output_dir: Optional[str] = None,
    cancel_event: Optional[threading.Event] = None,
    progress_callback: Optional[Callable[..., None]] = None,
) -> bool:
    """Download what an Instagram link or @username points to.

    ``media`` is ``all``, ``images`` or ``videos``. ``limit`` caps how many of
    a profile's newest posts are fetched. ``cookies`` is a Netscape
    cookies.txt file and ``browser`` a browser to read cookies from; either is
    needed for stories, highlights and private accounts. Files go to
    ``output_dir`` (default ``Downloads/Instagram``), one folder per account.
    """
    if media not in MEDIA_CHOICES:
        print_error(f"Unknown media type '{escape(media)}'. Use one of: {', '.join(MEDIA_CHOICES)}.")
        return False
    if limit is not None and limit < 1:
        print_error("The limit must be a positive number of posts.")
        return False

    kind, link = classify_url(url)
    if not kind:
        print_error(f"Not an Instagram link or username: {escape(url)}")
        return False

    if browser:
        browser = browser.strip().lower()
        if browser not in BROWSERS:
            print_error(f"Cannot read cookies from '{escape(browser)}'. "
                        f"Supported: {', '.join(BROWSERS)}.")
            return False

    cookie_file = None
    if cookies:
        cookie_file = os.path.abspath(os.path.expanduser(cookies))
        if not os.path.isfile(cookie_file):
            print_error(f"Cookies file not found: {escape(cookie_file)}")
            return False

    out_root = (os.path.abspath(os.path.expanduser(output_dir)) if output_dir
                else os.path.join(get_downloads_folder(), "Instagram"))
    try:
        os.makedirs(out_root, exist_ok=True)
    except OSError as exc:
        print_error(f"Cannot create {escape(out_root)}: {escape(str(exc))}")
        return False

    print_step(f"Saving to: [bold]{escape(out_root)}[/bold]")
    print_step(f"Downloading: {_MEDIA_LABELS[media]}")
    if cookie_file:
        print_step(f"Logged in with cookies from {escape(os.path.basename(cookie_file))}")
    elif browser:
        print_step(f"Logged in with cookies from {escape(browser)}")
    else:
        console.print("[dim]No login: public posts and profiles only.[/dim]")
        if needs_login(link):
            print_warning("Stories, highlights and share links usually need a login; "
                          "trying anyway.")

    if kind == "post":
        if limit:
            console.print("[dim]--limit only applies to profiles; the whole post is downloaded.[/dim]")
        return _download_post(link, media, out_root, cookie_file, browser,
                              cancel_event, progress_callback)
    return _download_collection(link, media, out_root, limit, cookie_file, browser,
                                cancel_event, progress_callback)


def _positive_int(value: str) -> int:
    try:
        number = int(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"'{value}' is not a whole number")
    if number < 1:
        raise argparse.ArgumentTypeError("must be 1 or more")
    return number


def main():
    """CLI entry point for the Instagram Downloader."""
    parser = ArgumentParser(
        description="Instagram Downloader: photos, videos, reels, carousels, "
                    "profiles, stories and highlights",
        epilog="Public posts and profiles work without logging in. Stories, "
               "highlights and private accounts need --cookies or --browser.",
    )
    parser.add_argument("url", help="Link to a post, reel, profile, stories or "
                                    "highlights, or a @username")
    parser.add_argument("--media", choices=MEDIA_CHOICES, default="all",
                        help="What to download (default: all)")
    parser.add_argument("--limit", type=_positive_int,
                        help="Profiles only: fetch just the newest N posts")
    parser.add_argument("--cookies", help=f"cookies.txt file exported from a browser "
                                          f"where you are logged in (default: ${COOKIES_ENV})")
    parser.add_argument("--browser", choices=BROWSERS, type=str.lower,
                        help="Read the login cookies from this browser instead")
    parser.add_argument("--out-dir", help="Folder to save into (default: Downloads/Instagram)")
    args = parser.parse_args()

    load_environment()
    cookies = args.cookies or (None if args.browser else get_env_var(COOKIES_ENV) or None)
    try:
        result = run_instagram_downloader(
            args.url, media=args.media, limit=args.limit, cookies=cookies,
            browser=args.browser, output_dir=args.out_dir)
    except KeyboardInterrupt:
        raise SystemExit(130)
    raise SystemExit(exit_code(result))


if __name__ == "__main__":
    main()
