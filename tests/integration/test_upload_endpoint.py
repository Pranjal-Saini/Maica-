from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_upload_stores_raw_evidence_with_provenance(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_messy.csv").read_bytes()

    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("saved_search_messy.csv", csv_bytes, "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert len(body["files"]) == 1
    file_result = body["files"][0]
    assert file_result["evidence_type"] == "saved_search_csv"  # auto-detected
    raw_evidence = file_result["raw_evidence"]
    assert raw_evidence["source_type"] == "upload:saved_search_csv"
    assert raw_evidence["tenant_id"] == tenant_id
    assert raw_evidence["understood_summary"]["rows_understood"] == 3
    assert raw_evidence["understood_summary"]["rows_skipped"] == 1
    assert raw_evidence["unavailable_reason"] is None
    # messy fixture: 3 understood rows x 5 data fields (entity, amount, account,
    # memo, custom field 1) each = 15 normalized records
    assert body["records_created"] == 15
    assert any("unparseable" in note for note in file_result["normalization_notes"])


async def test_upload_of_empty_file_reports_it_as_unrecognised(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("empty.csv", b"", "text/csv")},
    )

    assert response.status_code == 200
    body = response.json()
    assert "empty" in body["files"][0]["unrecognised_reason"]
    assert body["records_created"] == 0


async def test_upload_of_undetectable_file_is_named_not_guessed(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("mystery.csv", b"Foo,Bar\n1,2\n", "text/csv")},
    )

    assert response.status_code == 200
    file_result = response.json()["files"][0]
    assert file_result["evidence_type"] is None
    assert "Could not tell which kind" in file_result["unrecognised_reason"]


async def test_uploading_two_different_evidence_types_at_once(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    saved_search = (FIXTURES / "saved_search_clean.csv").read_bytes()
    system_notes = (FIXTURES / "system_notes_clean.csv").read_bytes()

    response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files=[
            ("files", ("saved_search_clean.csv", saved_search, "text/csv")),
            ("files", ("system_notes_clean.csv", system_notes, "text/csv")),
        ],
    )

    assert response.status_code == 200
    body = response.json()
    detected = {f["filename"]: f["evidence_type"] for f in body["files"]}
    assert detected == {
        "saved_search_clean.csv": "saved_search_csv",
        "system_notes_clean.csv": "system_notes_csv",
    }
    # both landed in the same analysis: 12 saved-search + 3 system-notes records
    assert body["records_created"] == 15


async def test_upload_rejected_for_tenant_without_access(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    other_client_tenant_id = "00000000-0000-0000-0000-000000000099"
    response = await client.post(
        f"/tenants/{other_client_tenant_id}/uploads",
        files={"files": ("whatever.csv", b"a,b\n1,2\n", "text/csv")},
    )

    assert response.status_code == 403
