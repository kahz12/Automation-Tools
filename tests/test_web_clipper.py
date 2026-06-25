from bs4 import BeautifulSoup

from automation_tools.tools import web_clipper as wc


def test_slug():
    assert wc._slug("¡Hola, Mundo!") == "hola-mundo"
    assert wc._slug("") == "clip"


def test_ws_collapses_whitespace():
    assert wc._ws("a\n\n   b\t c") == "a b c"


def test_get_title_prefers_meta():
    soup = BeautifulSoup('<title>Plain</title>', "html.parser")
    assert wc._get_title(soup) == "Plain"
    soup2 = BeautifulSoup('<meta property="og:title" content="OG Title"><title>Plain</title>', "html.parser")
    assert wc._get_title(soup2) == "OG Title"


def test_extract_main_picks_article():
    body = "x " * 200  # > 200 chars of content
    soup = BeautifulSoup(f"<html><body><nav>menu</nav><article><p>{body}</p></article></body></html>", "html.parser")
    main = wc._extract_main(soup)
    assert main.name == "article"


def test_to_markdown_paragraph():
    soup = BeautifulSoup("<p>Hello <strong>world</strong></p>", "html.parser")
    md = wc._to_markdown(soup.find("p"), "https://x", include_images=False)
    assert "Hello" in md
    assert "**world**" in md


def test_plain_text():
    soup = BeautifulSoup("<div><p>one</p><p>two</p></div>", "html.parser")
    text = wc._plain_text(soup.find("div"))
    assert "one" in text and "two" in text
