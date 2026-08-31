import uuid
from pathlib import Path

from httpx import AsyncClient

from tests.conftest import signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_graph_endpoint_renders_shared_field_relationships(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    graph_response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/graph")

    assert graph_response.status_code == 200
    text = graph_response.text
    assert "Record 1001 (Journal Entry)" in text
    assert "entity = 'Acme Corp' (shared with 1002)" in text
    assert "account = '4000 - Revenue' (shared with 1003)" in text


async def test_graph_endpoint_for_analysis_with_no_records(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")

    response = await client.get(f"/tenants/{tenant_id}/analyses/{uuid.uuid4()}/graph")

    assert response.status_code == 200
    assert response.text == "No records found for this analysis."


async def test_graph_endpoint_enforces_tenant_isolation(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    other_tenant_id = "00000000-0000-0000-0000-000000000099"
    other_tenant_response = await client.get(
        f"/tenants/{other_tenant_id}/analyses/{analysis_id}/graph"
    )

    assert other_tenant_response.status_code == 403
