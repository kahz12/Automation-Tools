import argparse
import os
import re
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

from automation_tools.core.logger import console, print_error, print_step, print_success, print_warning

# --- Web Clipper ---
# Fetch a web page, strip away the chrome (nav, ads, scripts…), isolate the
# main article and save it as clean Markdown or plain text. Built only on
# `requests` + `beautifulsoup4` with the stdlib `html.parser`, so it needs no
# extra binaries and runs the same on Linux, Windows and Termux/Android.
# The saved file chains nicely into the Summarizer and Translator tools.

try:
    import requests
    from bs4 import BeautifulSoup, Comment, NavigableString, Tag
    HAS_DEPS = True
except ImportError:
    HAS_DEPS = False

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/124.0 Safari/537.36 AutomationTools/1.0"
)

# Tags that never carry article content.
_STRIP_TAGS = (
    "script", "style", "noscript", "nav", "header", "footer", "aside",
    "form", "iframe", "svg", "button", "input", "select", "textarea",
)
_CONTENT_HINT = re.compile(r"(article|content|post|entry|main|story|markdown|prose)", re.I)
_JUNK_HINT = re.compile(
    r"(nav|menu|sidebar|footer|header|comment|share|social|advert|\bad-|promo|"
    r"cookie|banner|related|newsletter|subscribe|popup|modal|breadcrumb)",
    re.I,
)


# ── fetching ─────────────────────────────────────────────────────────────────
def _fetch(url: str, timeout: int) -> str:
    """Download a page as text, with a browser-like UA and sane encoding."""
    resp = requests.get(
        url,
        headers={"User-Agent": USER_AGENT, "Accept-Language": "en,es;q=0.8"},
        timeout=timeout,
    )
    resp.raise_for_status()
    if not resp.encoding or resp.encoding.lower() == "iso-8859-1":
        resp.encoding = resp.apparent_encoding or resp.encoding
    return resp.text


# ── content isolation ────────────────────────────────────────────────────────
def _text_len(node) -> int:
    return len(node.get_text(strip=True)) if node else 0


def _attr_blob(node: "Tag") -> str:
    classes = node.get("class") or []
    return " ".join(classes) + " " + (node.get("id") or "")


def _score(node: "Tag") -> float:
    """Heuristic: paragraph text length, boosted/penalised by class & id hints."""
    paragraphs = node.find_all("p", recursive=True)
    score = float(sum(len(p.get_text(strip=True)) for p in paragraphs))
    blob = _attr_blob(node)
    if _JUNK_HINT.search(blob):
        score *= 0.3
    if _CONTENT_HINT.search(blob):
        score *= 1.5
    return score


def _extract_main(soup: "BeautifulSoup") -> Optional["Tag"]:
    """Return the subtree most likely to hold the article body."""
    for element in soup(list(_STRIP_TAGS)):
        element.decompose()
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # Trust semantic containers first.
    for selector in ("article", "main", "[role=main]"):
        node = soup.select_one(selector)
        if node and _text_len(node) > 200:
            return node

    # Otherwise pick the highest-scoring block container.
    best, best_score = None, 0.0
    for node in soup.find_all(["div", "section", "article"]):
        score = _score(node)
        if score > best_score:
            best, best_score = node, score
    return best or soup.body or soup


# ── HTML → Markdown ──────────────────────────────────────────────────────────
def _ws(text: str) -> str:
    return re.sub(r"\s+", " ", text)


def _to_markdown(node, base_url: str, include_images: bool) -> str:
    """Recursively render an element subtree into Markdown."""
    if isinstance(node, NavigableString):
        if isinstance(node, Comment):
            return ""
        return _ws(str(node))
    if not isinstance(node, Tag):
        return ""

    name = node.name.lower()

    def children() -> str:
        return "".join(_to_markdown(c, base_url, include_images) for c in node.children)

    if name in ("script", "style", "noscript"):
        return ""
    if name == "br":
        return "  \n"
    if name == "hr":
        return "\n\n---\n\n"
    if name in ("strong", "b"):
        inner = children().strip()
        return f"**{inner}**" if inner else ""
    if name in ("em", "i"):
        inner = children().strip()
        return f"*{inner}*" if inner else ""
    if name == "code" and node.find_parent("pre") is None:
        inner = node.get_text().strip()
        return f"`{inner}`" if inner else ""
    if name == "a":
        inner = children().strip() or (node.get("title") or "")
        href = node.get("href", "")
        if href:
            href = urljoin(base_url, href)
        return f"[{inner}]({href})" if inner and href else inner
    if name == "img":
        if not include_images:
            return ""
        src = node.get("src") or node.get("data-src") or ""
        if src:
            src = urljoin(base_url, src)
        return f"![{node.get('alt', '')}]({src})" if src else ""
    if name in ("h1", "h2", "h3", "h4", "h5", "h6"):
        inner = children().strip()
        return f"\n\n{'#' * int(name[1])} {inner}\n\n" if inner else ""
    if name == "p":
        inner = children().strip()
        return f"\n\n{inner}\n\n" if inner else ""
    if name == "blockquote":
        inner = children().strip()
        if not inner:
            return ""
        quoted = "\n".join(f"> {line}" for line in inner.splitlines())
        return f"\n\n{quoted}\n\n"
    if name == "pre":
        body = node.get_text().rstrip()
        return f"\n\n```\n{body}\n```\n\n" if body else ""
    if name in ("ul", "ol"):
        lines = []
        for i, li in enumerate(node.find_all("li", recursive=False), 1):
            item = _to_markdown(li, base_url, include_images).strip()
            if not item:
                continue
            prefix = f"{i}. " if name == "ol" else "- "
            lines.append(prefix + item.replace("\n", "\n  "))
        body = "\n".join(lines)
        return f"\n\n{body}\n\n" if body else ""
    # Generic container (div, section, span, li, article…) — render children.
    return children()


def _cleanup(markdown: str) -> str:
    markdown = re.sub(r"[ \t]+\n", "\n", markdown)
    markdown = re.sub(r"\n{3,}", "\n\n", markdown)
    return markdown.strip()


def _plain_text(node) -> str:
    lines = [ln.strip() for ln in node.get_text("\n").splitlines()]
    return "\n\n".join(ln for ln in lines if ln)


# ── metadata ─────────────────────────────────────────────────────────────────
def _meta(soup: "BeautifulSoup", *names: str) -> str:
    for name in names:
        tag = soup.find("meta", attrs={"property": name}) or soup.find("meta", attrs={"name": name})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return ""


def _get_title(soup: "BeautifulSoup") -> str:
    title = _meta(soup, "og:title", "twitter:title")
    if title:
        return title
    if soup.title and soup.title.string:
        return soup.title.string.strip()
    h1 = soup.find("h1")
    if h1:
        return h1.get_text(strip=True)
    return "Untitled clip"


def _slug(title: str) -> str:
    slug = re.sub(r"[^\w\s-]", "", title).strip().lower()
    slug = re.sub(r"[\s_-]+", "-", slug)
    return slug[:60] or "clip"


def _assemble(title: str, url: str, soup: "BeautifulSoup", body: str, fmt: str) -> str:
    description = _meta(soup, "og:description", "description")
    author = _meta(soup, "author", "article:author")
    stamp = datetime.now().strftime("%Y-%m-%d %H:%M")
    if fmt == "text":
        head = [title, "", f"Source: {url}", f"Clipped: {stamp}"]
        if author:
            head.insert(3, f"Author: {author}")
        return "\n".join(head) + "\n\n" + ("-" * 60) + "\n\n" + body
    # markdown
    head = [f"# {title}", "", f"> **Source:** <{url}>  ", f"> **Clipped:** {stamp}  "]
    if author:
        head.append(f"> **Author:** {author}  ")
    if description:
        head.append(f">\n> {description}")
    return "\n".join(head) + "\n\n---\n\n" + body


# ── main entry ───────────────────────────────────────────────────────────────
def run_web_clipper(
    url: str,
    out_path: Optional[str] = None,
    fmt: str = "markdown",
    include_images: bool = True,
    save: bool = False,
    timeout: int = 20,
) -> None:
    """Clip the main article of a web page to clean Markdown or plain text.

    Args:
        url: Page URL (the scheme defaults to https:// if omitted).
        out_path: Explicit output file. If empty and `save` is True, a name is
            derived from the page title.
        fmt: "markdown" (default) or "text".
        include_images: Keep image references in Markdown output.
        save: Save the result to disk (auto-named when `out_path` is empty).
        timeout: Network timeout in seconds.
    """
    if not HAS_DEPS:
        print_error("Missing dependencies. Install with 'pip install requests beautifulsoup4'.")
        return

    url = url.strip()
    if not re.match(r"^https?://", url, re.I):
        url = "https://" + url

    print_step(f"Fetching {url} …")
    try:
        html = _fetch(url, timeout)
    except requests.exceptions.Timeout:
        print_error(f"The request timed out after {timeout}s.")
        return
    except requests.exceptions.RequestException as e:
        print_error(f"Could not fetch the page: {e}")
        return

    soup = BeautifulSoup(html, "html.parser")
    title = _get_title(soup)
    main = _extract_main(soup)
    if main is None or _text_len(main) < 50:
        print_warning("Could not isolate the article — using the whole page text.")
        main = soup.body or soup

    fmt = "text" if fmt.lower() in ("text", "txt", "plain") else "markdown"
    if fmt == "text":
        body = _plain_text(main)
    else:
        body = _cleanup(_to_markdown(main, url, include_images))

    if not body.strip():
        print_error("No readable content was found on the page.")
        return

    document = _assemble(title, url, soup, body, fmt)
    print_step(f"“{title}” — ~{len(body.split())} words extracted.")

    # Render a styled preview in the console / TUI log.
    try:
        if fmt == "markdown":
            from rich.markdown import Markdown
            console.print(Markdown(document))
        else:
            console.print(document)
    except Exception:
        console.print(document)

    # Persist if requested.
    if out_path or save:
        ext = ".txt" if fmt == "text" else ".md"
        target = out_path.strip() if out_path and out_path.strip() else f"{_slug(title)}{ext}"
        if not os.path.splitext(target)[1]:
            target += ext
        try:
            with open(target, "w", encoding="utf-8") as fh:
                fh.write(document)
            print_success(f"Saved to '{target}'  ({len(document)} chars)")
        except OSError as e:
            print_error(f"Could not write '{target}': {e}")
    else:
        print_success("Done. Enable 'Save to file' to keep a copy.")


# ── CLI ────────────────────────────────────────────────────────────────────────
def main() -> None:
    parser = argparse.ArgumentParser(description="Clip a web page's main article to Markdown or text.")
    parser.add_argument("url", help="Page URL.")
    parser.add_argument("--text", action="store_true", help="Output plain text instead of Markdown.")
    parser.add_argument("--no-images", action="store_true", help="Drop image references (Markdown only).")
    parser.add_argument("--out", help="Output file path.")
    parser.add_argument("--save", action="store_true", help="Save with an auto-generated filename.")
    parser.add_argument("--timeout", type=int, default=20, help="Network timeout in seconds (default 20).")
    args = parser.parse_args()

    run_web_clipper(
        args.url,
        out_path=args.out,
        fmt="text" if args.text else "markdown",
        include_images=not args.no_images,
        save=args.save,
        timeout=args.timeout,
    )


if __name__ == "__main__":
    main()
