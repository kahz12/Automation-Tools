import pytest
from bs4 import BeautifulSoup

from automation_tools.tools import monitor

SETTINGS = {"decimal_separator": ".", "thousands_separator": ",", "currency_code": "USD"}


def test_clean_price():
    assert monitor.clean_price("$ 1,234.56", SETTINGS) == 1234.56
    assert monitor.clean_price("", SETTINGS) is None
    assert monitor.clean_price("sin numero", SETTINGS) is None


def test_clean_price_european_separators():
    eu = {"decimal_separator": ",", "thousands_separator": "."}
    assert monitor.clean_price("1.234,56", eu) == 1234.56


def test_format_price():
    assert monitor.format_price(1234.5, SETTINGS) == "1,234.50 USD"


def test_extract_ml_item_id():
    url = "https://articulo.mercadolibre.com.co/MCO-886072080-bota-de-caucho"
    assert monitor.extract_ml_item_id(url) == "MCO886072080"
    assert monitor.extract_ml_item_id("https://example.com/foo") is None


def test_check_mercadolibre_meta_price():
    soup = BeautifulSoup('<meta itemprop="price" content="1234.50">', "html.parser")
    assert monitor.check_mercadolibre("https://x", soup, SETTINGS) == 1234.5


def test_check_amazon_selector():
    soup = BeautifulSoup('<span class="a-price-whole">99</span>', "html.parser")
    assert monitor.check_amazon(soup, SETTINGS) == 99.0


def test_detect_stock():
    out = BeautifulSoup("<p>Producto agotado</p>", "html.parser")
    assert monitor.detect_stock(out, 10.0) is False
    ok = BeautifulSoup("<p>En venta</p>", "html.parser")
    assert monitor.detect_stock(ok, 10.0) is True
    assert monitor.detect_stock(ok, None) is False


def test_database_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setattr(monitor, "DB_FILE", str(tmp_path / "hist.db"))
    monitor.init_db()
    url = "https://x/item"
    assert monitor.obtener_ultimo_precio(url) is None
    monitor.guardar_precio("Item", url, 100.0, "USD")
    monitor.guardar_precio("Item", url, 80.0, "USD")
    assert monitor.obtener_ultimo_precio(url) in (80.0, 100.0)

    assert monitor.get_last_stock(url) is None
    monitor.save_stock(url, True)
    assert monitor.get_last_stock(url) is True
    monitor.save_stock(url, False)
    assert monitor.get_last_stock(url) is False


def test_latest_price_is_stable_when_timestamps_match(monkeypatch, tmp_path):
    monkeypatch.setattr(monitor, "DB_FILE", str(tmp_path / "hist.db"))
    monitor.init_db()
    url = "https://x/item"
    conn = monitor.sqlite3.connect(monitor.DB_FILE)
    conn.executemany(
        "INSERT INTO historial (nombre, url, precio, moneda, fecha) VALUES (?, ?, ?, ?, ?)",
        [("Item", url, 100.0, "USD", "2026-01-01 00:00:00"),
         ("Item", url, 80.0, "USD", "2026-01-01 00:00:00")],
    )
    conn.commit()
    conn.close()

    assert monitor.obtener_ultimo_precio(url) == 80.0


def test_db_connection_closes_even_when_a_query_raises(monkeypatch, tmp_path):
    """The handle must not leak when a statement fails inside the context."""
    monkeypatch.setattr(monitor, "DB_FILE", str(tmp_path / "hist.db"))
    monitor.init_db()

    opened = []
    real_connect = monitor.sqlite3.connect

    def spy(*args, **kwargs):
        conn = real_connect(*args, **kwargs)
        opened.append(conn)
        return conn

    monkeypatch.setattr(monitor.sqlite3, "connect", spy)

    with pytest.raises(monitor.sqlite3.OperationalError):
        with monitor._db() as conn:
            conn.execute("SELECT * FROM no_such_table")

    assert len(opened) == 1
    # Using a closed connection is the only way to observe that it is closed.
    with pytest.raises(monitor.sqlite3.ProgrammingError):
        opened[0].execute("SELECT 1")


def test_db_rolls_back_a_write_when_the_block_raises(monkeypatch, tmp_path):
    """A half-finished round must not leave a partial row behind."""
    monkeypatch.setattr(monitor, "DB_FILE", str(tmp_path / "hist.db"))
    monitor.init_db()
    url = "https://x/ghost"

    with pytest.raises(RuntimeError):
        with monitor._db() as conn:
            conn.execute(
                "INSERT INTO historial (nombre, url, precio, moneda, fecha) "
                "VALUES (?, ?, ?, ?, ?)",
                ("Ghost", url, 1.0, "USD", "2026-01-01 00:00:00"),
            )
            raise RuntimeError("interrupted mid-round")

    assert monitor.obtener_ultimo_precio(url) is None


def test_send_notification_escapes_html_and_markup(monkeypatch):
    sent = {}

    def fake_send_telegram(token, chat_id, msg):
        sent["msg"] = msg

    monkeypatch.setattr(monitor, "send_telegram", fake_send_telegram)
    monitor.send_notification(
        "Alert <script>",
        "Item [/] & <b onclick=evil()>link</b>",
        {"telegram_token": "tok", "telegram_chat_id": "123"},
    )
    assert "<script>" not in sent["msg"]
    assert "&lt;script&gt;" in sent["msg"]
    assert "&amp;" in sent["msg"]

