import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from fastapi.testclient import TestClient
from web.server import app

def test_server_endpoints():
    client = TestClient(app)
    
    # 1. Test filings endpoint
    resp = client.get("/api/filings")
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}"
    filings = resp.json()["filings"]
    assert len(filings) == 20, f"Expected 20 filings, got {len(filings)}"
    print(f"PASS: /api/filings returned {len(filings)} cases.")

    # 2. Test query endpoint (verified math)
    query_payload = {
        "case_id": "fb_msft_01",
        "ablation_mode": "full"
    }
    q_resp = client.post("/api/query", json=query_payload)
    assert q_resp.status_code == 200, f"Expected 200, got {q_resp.status_code}"
    q_data = q_resp.json()
    assert q_data["status"] == "VERIFIED"
    assert q_data["numeric_result"] == "16.82%"
    assert len(q_data["cited_cells"]) == 2
    print(f"PASS: /api/query verified result: {q_data['numeric_result']}")

    # 3. Test refusal query endpoint
    refusal_payload = {
        "case_id": "fb_refusal_01",
        "ablation_mode": "full"
    }
    r_resp = client.post("/api/query", json=refusal_payload)
    assert r_resp.status_code == 200
    r_data = r_resp.json()
    assert r_data["status"] == "REFUSAL"
    print(f"PASS: /api/query refusal triggered correctly: {r_data['refusal_reason']}")

    # 4. Test benchmark endpoint
    b_resp = client.get("/api/benchmark")
    assert b_resp.status_code == 200
    b_data = b_resp.json()
    assert len(b_data["benchmark"]) == 4
    ledger_row = b_data["benchmark"][3]
    assert ledger_row["accuracy"] >= 80.0
    print(f"PASS: /api/benchmark returned 4 ablations. Full Ledger Accuracy: {ledger_row['accuracy']}%")

    # 5. Test static index.html
    idx_resp = client.get("/")
    assert idx_resp.status_code == 200
    assert "LEDGER" in idx_resp.text
    print("PASS: / (index.html) successfully served.")

if __name__ == "__main__":
    test_server_endpoints()
    print("\nALL SERVER API TESTS PASSED (5/5)!")
