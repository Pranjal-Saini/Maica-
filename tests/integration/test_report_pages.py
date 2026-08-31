import uuid
from pathlib import Path

from httpx import AsyncClient

from tests.conftest import signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"


async def test_records_list_page_links_to_report(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report" in response.text
    assert f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1003/report" in response.text


async def test_records_list_page_with_no_records(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")

    response = await client.get(f"/tenants/{tenant_id}/analyses/{uuid.uuid4()}/records")

    assert response.status_code == 200
    assert "No records found" in response.text


async def test_report_page_renders_factors_gaps_and_next_step(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("saved_search_clean.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/1001/report")

    assert response.status_code == 200
    text = response.text
    assert "Record 1001" in text
    assert "UNCERTAIN" in text
    assert "What could not be checked" in text
    assert "Next thing worth looking at" in text
    assert "Start with the top-ranked factor" in text


async def test_report_page_for_record_with_no_correlations(client: AsyncClient) -> None:
    tenant_id = await signup_with_tenant(client, "consultant@example.com", "Acme Corp")
    csv_bytes = (
        b"Internal ID,Date,Type,Name,Amount,Account,Memo\n"
        b"5001,1/1/2026,Bill,Solo Vendor,10.00,9999 - Misc,Only row\n"
    )

    upload_response = await client.post(
        f"/tenants/{tenant_id}/uploads",
        files={"file": ("solo.csv", csv_bytes, "text/csv")},
    )
    analysis_id = upload_response.json()["raw_evidence"]["analysis_id"]

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records/5001/report")

    assert response.status_code == 200
    assert "No contributing factors were found" in response.text
    assert "uploading a System Notes export" in response.text
