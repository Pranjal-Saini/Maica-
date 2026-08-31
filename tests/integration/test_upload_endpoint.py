from pathlib import Path

from httpx import AsyncClient

from tests.conftest import signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_upload_stores_raw_evidence_with_provenance(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_messy.csv").read_bytes()

    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("saved_search_messy.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    raw_evidence = body["raw_evidence"]
    assert raw_evidence["source_type"] == "upload:saved_search_csv"
    assert raw_evidence["tenant_id"] == tenant_id
    assert raw_evidence["understood_summary"]["rows_understood"] == 3
    assert raw_evidence["understood_summary"]["rows_skipped"] == 1
    assert raw_evidence["unavailable_reason"] is None
    # messy fixture: 3 understood rows x 5 data fields (entity, amount, account,
    # memo, custom field 1) each = 15 normalized records
    assert body["records_created"] == 15
    assert any("unparseable" in note for note in body["normalization_notes"])


async def test_upload_of_empty_file_reports_unavailable(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")

    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["raw_evidence"]["unavailable_reason"] == "uploaded file was empty"
    assert body["records_created"] == 0


async def test_upload_rejected_for_tenant_without_access(client: AsyncClient) -> None:
    await signup_with_tenant(client, "consultant@example.com", "Acme Corp")

    other_client_tenant_id = "00000000-0000-0000-0000-000000000099"
    response = await client.post(
        f"/tenants/{other_client_tenant_id}/uploads",
        files={"file": ("whatever.csv", b"a,b\n1,2\n", "text/csv")},
    )

    assert response.status_code == 403
