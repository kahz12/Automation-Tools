"""Tests for the non-API parts of the Gemini-backed tools."""
from automation_tools.tools import summarizer, translator, readme_generator, gemini_utils


# ── summarizer ──────────────────────────────────────────────────────────────
def test_summarizer_chunk_text_short():
    assert summarizer._chunk_text("short text") == ["short text"]


def test_summarizer_chunk_text_long():
    big = "palabra " * 10000  # well over CHUNK_CHARS
    chunks = summarizer._chunk_text(big)
    assert len(chunks) > 1
    assert sum(len(c) for c in chunks) >= len(big.rstrip())


def test_extract_text_from_txt(tmp_path):
    f = tmp_path / "n.txt"
    f.write_text("hola mundo", encoding="utf-8")
    assert summarizer.extract_text_from_txt(str(f)) == "hola mundo"


def test_extract_text_from_pdf_returns_str(tmp_path, make_pdf):
    src = make_pdf(tmp_path / "d.pdf", pages=2)
    assert isinstance(summarizer.extract_text_from_pdf(src), str)


# ── translator ──────────────────────────────────────────────────────────────
def test_translator_cache_key_deterministic():
    k1 = translator._chunk_cache_key("hello", "es")
    k2 = translator._chunk_cache_key("hello", "es")
    k3 = translator._chunk_cache_key("hello", "fr")
    assert k1 == k2
    assert k1 != k3


def test_translator_read_file(tmp_path):
    f = tmp_path / "a.md"
    f.write_text("# title", encoding="utf-8")
    assert translator.read_file(str(f)) == "# title"


# ── readme_generator ─────────────────────────────────────────────────────────
def test_detect_primary_language_python(tmp_path):
    (tmp_path / "main.py").write_text("print('hi')")
    (tmp_path / "util.py").write_text("x = 1")
    assert readme_generator.detect_primary_language(str(tmp_path)) == "Python"


def test_detect_primary_language_stack_marker(tmp_path):
    (tmp_path / "package.json").write_text("{}")
    assert "Node" in readme_generator.detect_primary_language(str(tmp_path))


def test_get_project_tree(tmp_path):
    (tmp_path / "f.py").write_text("x")
    tree = readme_generator.get_project_tree(str(tmp_path))
    assert tmp_path.name in tree
    assert "f.py" in tree


def test_generate_toc():
    md = "# Title\n## Section A\n### Sub B\n"
    toc = readme_generator.generate_toc(md)
    assert "- [Section A](#section-a)" in toc
    assert "Sub B" in toc


# ── gemini_utils ─────────────────────────────────────────────────────────────
def test_is_rate_limit():
    assert gemini_utils._is_rate_limit(Exception("Error 429 too many requests")) is True
    assert gemini_utils._is_rate_limit(Exception("resource_exhausted")) is True
    assert gemini_utils._is_rate_limit(Exception("invalid argument")) is False


class _FakeResp:
    def __init__(self, text):
        self.text = text
        self.usage_metadata = None


class _FakeModels:
    def __init__(self):
        self.calls = []

    def generate_content(self, model, contents):
        self.calls.append((model, contents))
        return _FakeResp("ok")


class _FakeClient:
    def __init__(self):
        self.models = _FakeModels()


def test_generate_content_passes_text_prompt():
    client = _FakeClient()
    assert gemini_utils.generate_content(client, "hola") == "ok"
    _, contents = client.models.calls[0]
    assert contents == "hola"


def test_generate_vision_content_sends_image_and_prompt():
    client = _FakeClient()
    out = gemini_utils.generate_vision_content(client, "read this", b"\x89PNG\r\n", "image/png")
    assert out == "ok"
    _, contents = client.models.calls[0]
    # contents is [image_part, prompt] for a multimodal request
    assert isinstance(contents, list) and len(contents) == 2
    assert contents[1] == "read this"
