from maica.reasoning.models import Factor, FactorLabel
from maica.reasoning.rules import suggest_next_step


def test_suggests_upload_more_evidence_when_no_factors() -> None:
    suggestion = suggest_next_step([])
    assert "uploading a System Notes export" in suggestion


def test_suggests_top_ranked_factor_when_present() -> None:
    factor = Factor(
        label=FactorLabel.UNCERTAIN,
        rank=1,
        summary="Shares account = '4000 - Revenue' with 1 other record(s): 1003.",
        supporting_source_ids=["1001", "1003"],
    )
    suggestion = suggest_next_step([factor])
    assert "rank 1" in suggestion
    assert "4000 - Revenue" in suggestion
