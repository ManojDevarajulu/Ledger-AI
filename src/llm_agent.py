import os
import re
import json
from typing import Dict, Any, Optional, List
from pydantic import BaseModel, Field
import httpx

class CitedCell(BaseModel):
    row: str
    col: str
    val: float

class FinancialSynthesis(BaseModel):
    """Structured output schema for Financial LLM synthesis."""
    narrative: str
    cited_cells: List[Dict[str, Any]] = Field(default_factory=list)
    formula: Optional[str] = None
    numeric_result: Optional[str] = None
    should_refuse: bool = False
    refusal_reason: Optional[str] = None
    model_name: str = "ledger-hybrid-agent"

class FinancialLLMAgent:
    """
    Neuro-Symbolic Financial LLM Agent.
    
    Pairs generative language reasoning with deterministic arithmetic verification:
    1. Interprets natural language financial questions against retrieved SEC 10-K tables.
    2. Identifies specific row/column cell coordinates and extracts numeric variables.
    3. Formulates a symbolic mathematical expression (e.g., '(v1 - v2) / v2 * 100').
    4. Passes the expression to the sandboxed AST Verifier to eliminate LLM arithmetic hallucinations.
    
    Supports both OpenAI-compatible endpoints (when API key is provided)
    and an offline heuristic extraction engine (for local testing/CI).
    """

    SYSTEM_PROMPT = """You are an audit-grade financial analyst for SEC Form 10-K filings.
Your job is to answer the user's question using ONLY the provided audited financial table excerpts.

Rules:
1. Ground every number in specific row labels and column headers.
2. If the user asks for growth, margin, or ratio, specify the exact symbolic formula.
3. If the requested information is NOT reported or broken out in the table, set "should_refuse": true.
4. Output STRICT JSON conforming to this schema:
{
  "narrative": "Concise 2-3 sentence executive summary explaining the metric and business context.",
  "cited_cells": [
    {"row": "Exact Row Label", "col": "FY2024", "val": 12345.0}
  ],
  "formula": "(val_current - val_prior) / val_prior * 100",
  "should_refuse": false,
  "refusal_reason": null
}"""

    def __init__(
        self,
        api_key: Optional[str] = None,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        timeout: float = 20.0
    ):
        self.api_key = api_key or os.getenv("OPENAI_API_KEY", "")
        self.base_url = (base_url or os.getenv("OPENAI_BASE_URL", "https://api.openai.com/v1")).rstrip("/")
        self.model = model or os.getenv("OPENAI_MODEL", "gpt-4o-mini")
        self.timeout = timeout

    @property
    def is_live_llm_enabled(self) -> bool:
        """Returns True if an external LLM API key is configured."""
        return bool(self.api_key and self.api_key.strip())

    def synthesize(
        self,
        query: str,
        retrieved_context: str,
        table_title: str,
        company: str,
        fiscal_year: int
    ) -> FinancialSynthesis:
        """
        Executes generative financial reasoning over the retrieved table context.
        Uses OpenAI when API key is configured; otherwise uses deterministic fallback engine.
        """
        if self.is_live_llm_enabled:
            try:
                return self._call_live_llm(query, retrieved_context, table_title, company, fiscal_year)
            except Exception as e:
                # Log error and fall back gracefully to local engine
                print(f"[LLMAgent] External LLM call failed ({e}); falling back to local extractor.")

        return self._local_deterministic_synthesis(query, retrieved_context, table_title, company, fiscal_year)

    def _call_live_llm(
        self,
        query: str,
        context: str,
        table_title: str,
        company: str,
        fiscal_year: int
    ) -> FinancialSynthesis:
        """Invokes OpenAI Chat Completions API with structured JSON response."""
        user_prompt = f"""Company: {company}
Filing: Form 10-K (FY{fiscal_year})
Table: {table_title}

Audited Statement Excerpt:
{context}

Question:
{query}"""

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": user_prompt}
            ],
            "response_format": {"type": "json_object"},
            "temperature": 0.0
        }

        with httpx.Client(timeout=self.timeout) as client:
            resp = client.post(f"{self.base_url}/chat/completions", headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            raw_content = data["choices"][0]["message"]["content"]
            parsed = json.loads(raw_content)

            return FinancialSynthesis(
                narrative=parsed.get("narrative", "Analysis synthesized from audited filing tables."),
                cited_cells=parsed.get("cited_cells", []),
                formula=parsed.get("formula"),
                should_refuse=parsed.get("should_refuse", False),
                refusal_reason=parsed.get("refusal_reason"),
                model_name=self.model
            )

    def _local_deterministic_synthesis(
        self,
        query: str,
        context: str,
        table_title: str,
        company: str,
        fiscal_year: int
    ) -> FinancialSynthesis:
        """
        High-precision deterministic local reasoning engine.
        Extracts cited variables and formulates equations from structured table chunks.
        """
        lines = [l.strip() for l in context.split("\n") if l.strip()]
        
        # Extract potential numbers and rows
        data_rows = []
        for line in lines:
            if "|" in line:
                parts = [p.strip() for p in line.split("|") if p.strip()]
                if len(parts) >= 2:
                    row_name = parts[0]
                    # Find numerical values
                    nums = []
                    for p in parts[1:]:
                        clean_str = p.replace('$', '').replace(',', '').replace('%', '').strip()
                        try:
                            val = float(clean_str)
                            nums.append((p, val))
                        except ValueError:
                            pass
                    if nums:
                        data_rows.append((row_name, nums))

        if not data_rows:
            return FinancialSynthesis(
                narrative=f"Audited financial disclosures for {company} (FY{fiscal_year}): {context[:250]}...",
                cited_cells=[],
                formula=None,
                model_name="ledger-local-engine"
            )

        # Focus on the most query-relevant data row
        query_words = set(query.lower().split())
        best_row = max(data_rows, key=lambda r: len(set(r[0].lower().split()) & query_words))
        row_label, num_list = best_row

        cited = []
        formula = None
        narrative = ""

        if len(num_list) >= 2:
            # Pair of values (e.g. Current vs Prior Period)
            val_prior = num_list[0][1]
            val_current = num_list[1][1]
            
            cited.append({"row": row_label, "col": "Prior Period", "val": val_prior})
            cited.append({"row": row_label, "col": f"FY{fiscal_year}", "val": val_current})
            
            if "growth" in query.lower() or "percentage" in query.lower() or "change" in query.lower():
                formula = f"({val_current} - {val_prior}) / {val_prior} * 100"
                diff = val_current - val_prior
                pct = (diff / val_prior * 100) if val_prior != 0 else 0.0
                direction = "grew by" if pct >= 0 else "declined by"
                narrative = (
                    f"For {company}, {row_label} {direction} {abs(pct):.2f}% in FY{fiscal_year} "
                    f"({val_current:,.0f} compared to {val_prior:,.0f} in the prior period), "
                    f"grounded directly in the {table_title} disclosure."
                )
            else:
                formula = f"{val_current} - {val_prior}"
                narrative = (
                    f"In FY{fiscal_year}, {company}'s {row_label} was reported at {val_current:,.0f} "
                    f"versus {val_prior:,.0f} in the preceding comparative period."
                )
        else:
            single_val = num_list[0][1]
            cited.append({"row": row_label, "col": f"FY{fiscal_year}", "val": single_val})
            formula = f"{single_val}"
            narrative = f"According to the {table_title} for {company}, {row_label} was {single_val:,.0f} in FY{fiscal_year}."

        return FinancialSynthesis(
            narrative=narrative,
            cited_cells=cited,
            formula=formula,
            model_name="ledger-local-engine"
        )
