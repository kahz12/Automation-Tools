"""Tests for the non-API parts of the AI-backed text tools."""
import pytest

from automation_tools.ai.base import Capability, CapabilityError
from automation_tools.tools import summarizer, translator, readme_generator


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


# ── provider registry integration ────────────────────────────────────────────
class _StubProvider:
    """Records what the tool asked for and returns canned text."""

    def __init__(self):
        self.prompts = []

    def generate_text(self, prompt, *, system=None, model=None):
        self.prompts.append({"prompt": prompt, "system": system})
        return "SUMMARY"


@pytest.fixture
def captured_provider(monkeypatch):
    """Intercepts get_provider in all three tools; returns (stub, calls)."""
    stub = _StubProvider()
    calls = []

    def fake_get_provider(capability, name=None, api_key=None, model=None):
        calls.append({"capability": capability, "name": name,
                      "api_key": api_key, "model": model})
        return stub

    for module in (summarizer, translator, readme_generator):
        monkeypatch.setattr(module, "get_provider", fake_get_provider)
    return stub, calls


def test_summarizer_asks_for_a_text_provider(tmp_path, captured_provider):
    _stub, calls = captured_provider
    doc = tmp_path / "doc.txt"
    doc.write_text("Some content to summarize.", encoding="utf-8")

    summarizer.run_summarizer(str(doc))

    assert calls[0]["capability"] is Capability.TEXT
    assert calls[0]["name"] is None, "no provider given means the registry decides"


def test_summarizer_forwards_provider_and_model(tmp_path, captured_provider):
    _stub, calls = captured_provider
    doc = tmp_path / "doc.txt"
    doc.write_text("Some content to summarize.", encoding="utf-8")

    summarizer.run_summarizer(str(doc), provider="groq", model="openai/gpt-oss-20b")

    assert calls[0]["name"] == "groq"
    assert calls[0]["model"] == "openai/gpt-oss-20b"


def test_summarizer_reports_a_provider_error_instead_of_raising(tmp_path, monkeypatch, capsys):
    doc = tmp_path / "doc.txt"
    doc.write_text("Some content.", encoding="utf-8")

    def boom(capability, name=None, api_key=None, model=None):
        raise CapabilityError("'deepseek' does not support vision.")

    monkeypatch.setattr(summarizer, "get_provider", boom)
    summarizer.run_summarizer(str(doc), provider="deepseek")

    assert "does not support" in capsys.readouterr().out


def test_translator_asks_for_a_text_provider(tmp_path, captured_provider):
    _stub, calls = captured_provider
    doc = tmp_path / "doc.txt"
    doc.write_text("Hello world.", encoding="utf-8")

    translator.run_translator(str(doc), "Spanish", provider="anthropic")

    assert calls[0]["capability"] is Capability.TEXT
    assert calls[0]["name"] == "anthropic"


def test_readme_generator_asks_for_a_text_provider(tmp_path, captured_provider):
    stub, calls = captured_provider
    (tmp_path / "app.py").write_text("print('hi')\n", encoding="utf-8")

    readme_generator.run_readme_generator(
        str(tmp_path), out_path=str(tmp_path / "README_generado.md"),
        provider="groq", model="openai/gpt-oss-20b",
    )

    assert calls[0]["capability"] is Capability.TEXT
    assert calls[0]["name"] == "groq"
    assert calls[0]["model"] == "openai/gpt-oss-20b"
    # The instruction has to reach the provider as `system=`, not the old
    # `system_instruction=` keyword, where a leftover is a runtime TypeError.
    assert "README.md" in stub.prompts[0]["system"]
