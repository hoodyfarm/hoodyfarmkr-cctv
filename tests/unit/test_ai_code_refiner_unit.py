import pytest
from src.services.ai_code_refiner import AICodeRefinerService
from src.schemas.ai_schema import AICodeFixSuggestionSchema

def test_ai_code_refiner_simulation_mode():
    """Verify AICodeRefinerService returns valid AICodeFixSuggestionSchema in simulation mode."""
    refiner = AICodeRefinerService(api_key="your_gemini_api_key_here")
    
    sample_tb = "ConnectionResetError: [Errno 104] Connection reset by peer"
    sample_code = "async def sync_db(): await db.execute('SELECT 1')"
    
    result = refiner.analyze_error_and_refine(sample_tb, sample_code)
    
    assert isinstance(result, AICodeFixSuggestionSchema)
    assert result.error_summary != ""
    assert result.root_cause != ""
    assert result.proposed_fix != ""
    assert "async" in result.refactored_code_snippet or "def" in result.refactored_code_snippet
