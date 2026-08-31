from pathlib import Path

from httpx import AsyncClient

from tests.conftest import signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_factors_endpoint_returns_ranked_uncertain_factors_and_gaps(
    client: AsyncClient,
) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/factors")

    assert response.status_code == 200
    body = response.json()
    assert body["target_source_id"] == "1001"
    assert len(body["factors"]) == 2
    assert all(f["label"] == "UNCERTAIN" for f in body["factors"])
    assert any("configuration-change evidence" in g["description"] for g in body["gaps"])


async def test_factors_endpoint_for_unknown_source_id(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/9999/factors")

    assert response.status_code == 200
    body = response.json()
    assert body["factors"] == []
    assert "9999" in body["gaps"][0]["description"]
