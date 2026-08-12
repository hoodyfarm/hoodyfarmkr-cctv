import pytest
from src.services.orchestrator import PipelineOrchestrator

@pytest.mark.asyncio
@pytest.mark.unit
async def test_pipeline_orchestrator_single_cycle():
    orchestrator = PipelineOrchestrator()
    result = await orchestrator.run_pipeline_cycle()

    assert result is not None
    assert result.get("status") == "success"
    assert "cycle_id" in result
    assert "ai_result" in result
    assert "is_anomaly" in result["ai_result"]
