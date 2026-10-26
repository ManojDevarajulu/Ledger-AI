import json
from decimal import Decimal
from pathlib import Path

def test_financebench_data_integrity():
    data_path = Path(__file__).parent.parent / "data" / "financebench_sample.jsonl"
    assert data_path.exists(), f"Data file not found at {data_path}"
    
    cases = []
    with open(data_path, "r", encoding="utf-8") as f:
        for idx, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            case = json.loads(line)
            cases.append(case)
            
    assert len(cases) == 20, f"Expected 20 cases, got {len(cases)}"
    
    math_cases = [c for c in cases if not c["is_refusal_case"]]
    refusal_cases = [c for c in cases if c["is_refusal_case"]]
    
    assert len(math_cases) == 16, f"Expected 16 math cases, got {len(math_cases)}"
    assert len(refusal_cases) == 4, f"Expected 4 refusal cases, got {len(refusal_cases)}"
    
    # Verify math consistency for every non-refusal case
    for case in math_cases:
        formula = case["formula"]
        expected_number = case["ground_truth_number"]
        assert formula is not None
        assert expected_number is not None
        
        # Safe eval using eval only in test to verify dataset ground truth
        calculated = eval(formula)
        diff = abs(calculated - expected_number)
        assert diff < 0.05, f"Case {case['case_id']}: formula {formula} = {calculated}, expected {expected_number}"

if __name__ == "__main__":
    test_financebench_data_integrity()
    print("SUCCESS: All 20 FinanceBench test cases verified and mathematically accurate!")
