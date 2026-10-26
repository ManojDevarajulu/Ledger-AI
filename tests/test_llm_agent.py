import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.llm_agent import FinancialLLMAgent, FinancialSynthesis

def test_llm_agent_initialization():
    agent_default = FinancialLLMAgent(api_key="")
    assert not agent_default.is_live_llm_enabled
    assert agent_default.model == "gpt-4o-mini"

    agent_custom = FinancialLLMAgent(api_key="sk-test-key", model="gpt-4o")
    assert agent_custom.is_live_llm_enabled
    assert agent_custom.model == "gpt-4o"
    print("[PASS] test_llm_agent_initialization")

def test_llm_agent_local_synthesis():
    agent = FinancialLLMAgent(api_key="")
    sample_context = """
    | Segment | FY2022 | FY2023 |
    |---|---|---|
    | Intelligent Cloud | 75,251 | 87,907 |
    | Productivity and Business | 63,364 | 69,274 |
    """
    
    result = agent.synthesize(
        query="What was the growth percentage of Intelligent Cloud in FY2023?",
        retrieved_context=sample_context,
        table_title="Segment Revenue",
        company="Microsoft Corporation",
        fiscal_year=2023
    )

    assert isinstance(result, FinancialSynthesis)
    assert len(result.cited_cells) == 2
    assert result.formula == "(87907.0 - 75251.0) / 75251.0 * 100"
    assert "Intelligent Cloud" in result.narrative
    assert "87,907" in result.narrative
    assert result.model_name == "ledger-local-engine"
    print(f"[PASS] test_llm_agent_local_synthesis: Formula -> {result.formula}")

def test_llm_agent_schema_validation():
    synth = FinancialSynthesis(
        narrative="Test narrative",
        cited_cells=[{"row": "Cloud", "col": "2023", "val": 100.0}],
        formula="(100 - 80) / 80",
        numeric_result="25.0%"
    )
    assert synth.narrative == "Test narrative"
    assert len(synth.cited_cells) == 1
    assert not synth.should_refuse
    print("[PASS] test_llm_agent_schema_validation")

if __name__ == "__main__":
    test_llm_agent_initialization()
    test_llm_agent_local_synthesis()
    test_llm_agent_schema_validation()
    print("\nALL LLM AGENT TESTS PASSED!")
