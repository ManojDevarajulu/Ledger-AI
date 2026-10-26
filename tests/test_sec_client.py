import sys
import shutil
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.sec_client import SECClient

def test_sec_client_cik_resolution():
    client = SECClient()
    # Test top tickers against fallback/live mapping
    msft_cik = client.get_cik("MSFT")
    aapl_cik = client.get_cik("AAPL")
    nvda_cik = client.get_cik("NVDA")
    tsla_cik = client.get_cik("TSLA")

    assert msft_cik == "0000789019", f"Expected MSFT CIK 0000789019, got {msft_cik}"
    assert aapl_cik == "0000320193", f"Expected AAPL CIK 0000320193, got {aapl_cik}"
    assert nvda_cik == "0001045810", f"Expected NVDA CIK 0001045810, got {nvda_cik}"
    assert tsla_cik == "0001318605", f"Expected TSLA CIK 0001318605, got {tsla_cik}"
    print("[PASS] test_sec_client_cik_resolution")

def test_sec_client_user_agent_and_headers():
    client = SECClient(user_agent="LedgerAudit/1.0 (test@ledgerai.local)")
    assert "User-Agent" in client.headers
    assert "LedgerAudit/1.0" in client.headers["User-Agent"]
    assert client.headers["Host"] == "www.sec.gov"
    assert client.submissions_headers["Host"] == "data.sec.gov"
    print("[PASS] test_sec_client_user_agent_and_headers")

def test_sec_client_table_extraction():
    client = SECClient()
    sample_html = """
    <html>
        <body>
            <p>Table of Contents</p>
            <table><tr><td>Item 1</td><td>Item 2</td></tr></table>
            <p><strong>Note 17 - Consolidated Revenue by Segment</strong></p>
            <table>
                <tr><th>Segment</th><th>FY2023</th><th>FY2022</th></tr>
                <tr><td>Cloud Services</td><td>87,907</td><td>75,251</td></tr>
                <tr><td>Productivity</td><td>69,274</td><td>63,364</td></tr>
                <tr><td>Personal Computing</td><td>54,734</td><td>59,655</td></tr>
                <tr><td>Total Revenue</td><td>211,915</td><td>198,270</td></tr>
            </table>
        </body>
    </html>
    """
    tables = client.extract_financial_tables(sample_html)
    assert len(tables) == 1, f"Expected 1 extracted financial table, got {len(tables)}"
    assert "Note 17" in tables[0]["title"] or "Segment" in tables[0]["title"]
    assert tables[0]["num_rows"] == 5
    assert tables[0]["num_data_cells"] >= 8
    print("[PASS] test_sec_client_table_extraction")

def test_sec_client_cache_structure(tmp_path):
    test_cache = Path(tmp_path) / "test_edgar_cache"
    client = SECClient(cache_dir=test_cache)
    assert test_cache.exists()
    assert client.cache_dir == test_cache
    print("[PASS] test_sec_client_cache_structure")

if __name__ == "__main__":
    import tempfile
    test_sec_client_cik_resolution()
    test_sec_client_user_agent_and_headers()
    test_sec_client_table_extraction()
    with tempfile.TemporaryDirectory() as td:
        test_sec_client_cache_structure(td)
    print("\nALL SEC CLIENT TESTS PASSED.")
