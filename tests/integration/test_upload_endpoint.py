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
    assert body["source_type"] == "upload:saved_search_csv"
    assert body["tenant_id"] == "11111111-1111-1111-1111-111111111111"
    assert body["understood_summary"]["rows_understood"] == 3
    assert body["understood_summary"]["rows_skipped"] == 1
    assert body["unavailable_reason"] is None


async def test_upload_of_empty_file_reports_unavailable(client: AsyncClient) -> None:
    response = await client.post(
        "/uploads",
        files={"file": ("empty.csv", b"", "text/csv")},
        headers={"X-Tenant-Id": "11111111-1111-1111-1111-111111111111"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["unavailable_reason"] == "uploaded file was empty"
