from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_uploading_system_notes_into_existing_analysis_combines_evidence(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    saved_search_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    first_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        data={"evidence_type": "saved_search_csv"},
        files={"files": ("saved_search_clean.csv", saved_search_bytes, "text/csv")},
    )
    analysis_id = first_response.json()["analysis_id"]

    system_notes_bytes = (FIXTURES / "system_notes_clean.csv").read_bytes()
    second_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        data={"evidence_type": "system_notes_csv", "analysis_id": analysis_id},
        files={"files": ("system_notes_clean.csv", system_notes_bytes, "text/csv")},
    )

    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["analysis_id"] == analysis_id
    assert second_body["records_created"] == 3

    factors_response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/factors"
    )
    body = factors_response.json()

    # 1001 has 2 field-change factors (Amount, Status) from system notes, plus
    # the pre-existing shared-value factors from the saved-search upload.
    change_factors = [f for f in body["factors"] if "went from" in f["summary"]]
    assert len(change_factors) == 2
    assert body["factors"][0] in change_factors  # change factors rank first
    assert not any(
        "No script, workflow, integration, or configuration-change evidence" in g["description"]
        for g in body["gaps"]
    )


async def test_upload_with_unknown_evidence_type_is_rejected(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        data={"evidence_type": "not_a_real_type"},
        files={"files": ("whatever.csv", b"a,b\n1,2\n", "text/csv")},
    )

    assert response.status_code == 422
    assert "not_a_real_type" in response.json()["error"]["message"]
