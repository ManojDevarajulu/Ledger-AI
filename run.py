import sys
import webbrowser
import threading
import time
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

import uvicorn

def open_browser():
    time.sleep(1.2)
    url = "http://127.0.0.1:8000"
    print(f"\n[LEDGER] Launching Financial Terminal at: {url}\n")
    try:
        webbrowser.open(url)
    except Exception as e:
        print(f"Notice: Open {url} manually in your browser ({e})")

def main():
    print("=" * 70)
    print("  LEDGER AI // Audit-Grade Financial RAG Terminal")
    print("  Table-Aware Retrieval + Deterministic Cell Verification")
    print("=" * 70)
    
    # Launch browser on separate thread
    threading.Thread(target=open_browser, daemon=True).start()
    
    # Run uvicorn server bound strictly to localhost
    uvicorn.run("web.server:app", host="127.0.0.1", port=8000, log_level="info")

if __name__ == "__main__":
    main()
