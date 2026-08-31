from pathlib import Path

from httpx import AsyncClient

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_upload_stores_raw_evidence_with_provenance(client: AsyncClient) -> None:
    csv_bytes = (FIXTURES / "saved_search_messy.csv").read_bytes()

    response = await client.post(
        "/uploads",
        files={"file": ("saved_search_messy.csv", csv_bytes, "text/csv")},
        headers={"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"},
    )

    assert response.status_code == 200
    body = response.json()
    raw_evidence = body["raw_evidence"]
    assert raw_evidence["source_type"] == "upload:saved_search_csv"
    assert raw_evidence["tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert raw_evidence["understood_summary"]["rows_understood"] == 3
    assert raw_evidence["understood_summary"]["rows_skipped"] == 1
    assert raw_evidence["unavailable_reason"] is None
    # messy fixture: 3 understood rows x 5 data fields (entity, amount, account,
    # memo, custom field 1) each = 15 normalized records
    assert body["records_created"] == 15
    assert any("unparseable" in note for note in body["normalization_notes"])


async def test_upload_of_empty_file_reports_unavailable(client: AsyncClient) -> None:
    response = await client.post(
        "/uploads",
        files={"file": ("empty.csv", b"", "text/csv")},
        headers={"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["raw_evidence"]["unavailable_reason"] == "uploaded file was empty"
    assert body["records_created"] == 0
