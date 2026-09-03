import re
import uuid
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.shortlist import SHORTLIST_LIMIT
from tests.conftest import signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_deep_dive_names_a_shortlist_not_every_record(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """It used to render one card per record, linking to each report. On a real
    account that is 10,000 links ordered by nothing that matters. It now names a
    ranked handful — record links are expected here, but only a few of them."""
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "Start here" in response.text
    linked = set(re.findall(r"/records/([^/\"]+)/report", response.text))
    assert 0 < len(linked) <= SHORTLIST_LIMIT


async def test_jump_to_record_still_reaches_its_report(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Grouping is for the consultant who does not know the ID. One who does
    # must not be made to hunt through patterns for it.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    analysis_id = (
        await client.post(
            f"/tenants/{tenant_id}/uploads",
            files={"files": ("saved_search_clean.csv", csv_bytes, "text/csv")},
        )
    ).json()["analysis_id"]

    found = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records?q=1001")
    missing = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records?q=999999")

    assert found.status_code == 303
    assert found.headers["location"].endswith("/records/1001/report")
    assert missing.status_code == 200
    assert "No record with ID" in missing.text


async def test_records_list_page_with_no_records(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    response = await client.get(f"/tenants/{tenant_id}/analyses/{uuid.uuid4()}/records")

    assert response.status_code == 200
    assert "No records found" in response.text


async def test_report_page_renders_factors_gaps_and_next_step(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    assert response.status_code == 200
    text = response.text
    assert "Record 1001" in text
    assert "UNCERTAIN" in text
    assert "What could not be checked" in text
    assert "Next thing worth looking at" in text
    assert "Start with the top-ranked factor" in text


async def test_report_page_for_record_with_no_correlations(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (
        b"Internal ID,Date,Type,Name,Amount,Account,Memo\n"
        b"5001,1/1/2026,Bill,Solo Vendor,10.00,9999 - Misc,Only row\n"
    )

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"files": ("solo.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/5001/report")

    assert response.status_code == 200
    assert "No contributing factors were found" in response.text
    assert "uploading a System Notes export" in response.text
