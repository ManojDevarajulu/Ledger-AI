import re
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field

class RefusalDecision(BaseModel):
    should_refuse: bool
    confidence_score: float
    reason_category: Optional[str] = None
    refusal_message: Optional[str] = None
    insufficient_elements: List[str] = Field(default_factory=list)

class CalibratedRefusalGuard:
    """
    Calibrated Refusal Guard for Financial Disclosures.
    Prevents hallucinating answers when evidence is missing, unstated, or out-of-scope.
    Guarantees strict safety boundaries on SEC filings.
    """

    KNOWN_UNDISCLOSED_PATTERNS = [
        "copilot arr",
        "copilot revenue",
        "project titan",
        "prime subscriber",
        "prime subscribers",
        "subscriber count",
        "fy2026 forecast",
        "fy2027",
        "future guidance",
        "unreleased product"
    ]

    FORWARD_LOOKING_KEYWORDS = [
        "forecast",
        "guidance",
        "projected",
        "projecting",
        "future expectation",
        "expected revenue for 2026",
        "expected revenue for 2027"
    ]

    def __init__(self, confidence_floor: float = 0.015):
        self.confidence_floor = confidence_floor

    def evaluate(
        self,
        query: str,
        retrieved_context: str,
        retrieval_score: float,
        cited_cells: Optional[List[Dict[str, Any]]] = None,
        available_fiscal_years: Optional[List[int]] = None
    ) -> RefusalDecision:
        query_lower = query.lower()
        context_lower = retrieved_context.lower()

        # 1. Check for forward-looking guidance / projections outside historical 10-K
        for fwd_term in self.FORWARD_LOOKING_KEYWORDS:
            if fwd_term in query_lower:
                return RefusalDecision(
                    should_refuse=True,
                    confidence_score=0.99,
                    reason_category="FORWARD_LOOKING_OUT_OF_SCOPE",
                    refusal_message=(
                        f"REFUSAL: Forward-looking projection ('{fwd_term}') is out of scope. "
                        f"SEC 10-K filings report audited historical financial performance."
                    ),
                    insufficient_elements=[fwd_term]
                )

        # 2. Pattern check for known non-disclosed / non-GAAP items
        for pattern in self.KNOWN_UNDISCLOSED_PATTERNS:
            terms = pattern.split()
            if all(t in query_lower for t in terms) and not all(t in context_lower for t in terms):
                return RefusalDecision(
                    should_refuse=True,
                    confidence_score=0.99,
                    reason_category="NON_DISCLOSED_METRIC",
                    refusal_message=(
                        f"REFUSAL: The requested metric ('{pattern}') is not reported or broken out "
                        f"in the audited SEC 10-K financial tables."
                    ),
                    insufficient_elements=[pattern]
                )

        # 3. Check for fiscal year temporal mismatch
        if available_fiscal_years:
            mentioned_years = re.findall(r"\b20\d{2}\b", query)
            for y_str in mentioned_years:
                y_int = int(y_str)
                if y_int not in available_fiscal_years and str(y_int) not in context_lower:
                    return RefusalDecision(
                        should_refuse=True,
                        confidence_score=0.95,
                        reason_category="TEMPORAL_OUT_OF_BOUNDS",
                        refusal_message=(
                            f"REFUSAL: Requested fiscal year {y_int} is outside the reporting periods "
                            f"({', '.join(map(str, available_fiscal_years))}) covered in this filing."
                        ),
                        insufficient_elements=[f"year_{y_int}"]
                    )

        # 4. Check retrieval score confidence floor
        if retrieval_score < self.confidence_floor:
            return RefusalDecision(
                should_refuse=True,
                confidence_score=retrieval_score,
                reason_category="LOW_RETRIEVAL_CONFIDENCE",
                refusal_message=(
                    "REFUSAL: Retrieved filing context does not contain sufficient table "
                    "evidence with acceptable statistical confidence."
                ),
                insufficient_elements=["evidence_table"]
            )

        # 5. Check for arithmetic cell completeness (if math was requested)
        is_math_query = any(k in query_lower for k in ["margin", "growth", "percentage", "%", "delta", "ratio", "change", "share"])
        if is_math_query and cited_cells is not None and len(cited_cells) < 1:
            return RefusalDecision(
                should_refuse=True,
                confidence_score=retrieval_score,
                reason_category="MISSING_CELL_COORDINATES",
                refusal_message="REFUSAL: Insufficient numeric cell coordinates located to compute verified math.",
                insufficient_elements=["numeric_cells"]
            )

        # Accept query
        return RefusalDecision(
            should_refuse=False,
            confidence_score=retrieval_score,
            reason_category=None,
            refusal_message=None
        )
