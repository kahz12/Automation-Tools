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
