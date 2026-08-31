import uuid
from pathlib import Path

from httpx import AsyncClient

FIXTURES = Path(__file__).parent.parent / "fixtures"
TENANT_ID = "44444444-4444-4444-4444-444444444444"


async def test_graph_endpoint_renders_shared_field_relationships(client: AsyncClient) -> None:
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        "/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
        headers={"X-Tenant-Id": TENANT_ID},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    graph_response = await client.get(
        f"/analyses/{analysis_id}/graph", headers={"X-Tenant-Id": TENANT_ID}
    )

    assert graph_response.status_code == 200
    text = graph_response.text
    assert "Record 1001 (Journal Entry)" in text
    assert "entity = 'Acme Corp' (shared with 1002)" in text
    assert "account = '4000 - Revenue' (shared with 1003)" in text


async def test_graph_endpoint_for_analysis_with_no_records(client: AsyncClient) -> None:
    response = await client.get(
        f"/analyses/{uuid.uuid4()}/graph", headers={"X-Tenant-Id": TENANT_ID}
    )

    assert response.status_code == 200
    assert response.text == "No records found for this analysis."


async def test_graph_endpoint_enforces_tenant_isolation(client: AsyncClient) -> None:
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        "/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
        headers={"X-Tenant-Id": TENANT_ID},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    other_tenant_response = await client.get(
        f"/analyses/{analysis_id}/graph",
        headers={"X-Tenant-Id": "55555555-5555-5555-5555-555555555555"},
    )

    assert other_tenant_response.text == "No records found for this analysis."
