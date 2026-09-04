"""Naming the symptom, and getting an answer rather than leads.

The scenario throughout: an automated process rewrote Account on three
invoices, and the consultant knows those three posted wrong. The comparison
should name that process, and nothing else.
"""

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from maica.api.routes.investigate import MAX_PASTED_IDS, parse_record_ids
from tests.conftest import login_as, logout, signup_with_tenant

# 4471-4473 were reclassified by System on a schedule. 4481-4483 were not, and
# went through the ordinary manual route instead.
NOTES = (
    b"Internal ID,Record Type,Date,Field,Old Value,New Value,Set By,Context,Type\n"
    b"4471,Invoice,7/12/2026 09:15,Account,4000,4010,System,SCHEDULED,Change\n"
    b"4472,Invoice,7/12/2026 09:16,Account,4000,4010,System,SCHEDULED,Change\n"
    b"4473,Invoice,7/12/2026 09:17,Account,4000,4010,System,SCHEDULED,Change\n"
    b"4471,Invoice,7/12/2026 10:00,Status,Open,Approved,jsmith,UI,Change\n"
    b"4472,Invoice,7/12/2026 10:01,Status,Open,Approved,jsmith,UI,Change\n"
    b"4481,Invoice,7/12/2026 11:00,Status,Open,Approved,jsmith,UI,Change\n"
    b"4482,Invoice,7/12/2026 11:01,Status,Open,Approved,mchen,UI,Change\n"
    b"4483,Invoice,7/12/2026 11:02,Status,Open,Approved,mchen,UI,Change\n"
    b"4481,Invoice,7/12/2026 11:30,Approval,Pending,Signed,mchen,WORKFLOW,Change\n"
    b"4482,Invoice,7/12/2026 11:31,Approval,Pending,Signed,mchen,WORKFLOW,Change\n"
    b"4483,Invoice,7/12/2026 11:32,Approval,Pending,Signed,mchen,WORKFLOW,Change\n"
)


async def _upload(client: AsyncClient, tenant_id: str) -> str:
    response = await client.post(
        f"/tenants/{tenant_id}/uploads", files={"files": ("notes.csv", NOTES, "text/csv")}
    )
    return response.json()["analysis_id"]


def test_pasted_ids_are_accepted_however_they_were_copied() -> None:
    assert parse_record_ids("4471, 4472,4473") == ["4471", "4472", "4473"]
    assert parse_record_ids("4471\n4472\n4473") == ["4471", "4472", "4473"]
    assert parse_record_ids("  4471   4472 ") == ["4471", "4472"]
    assert parse_record_ids("") == []
    assert len(parse_record_ids(" ".join(str(n) for n in range(MAX_PASTED_IDS + 50)))) == (
        MAX_PASTED_IDS
    )


async def test_naming_the_broken_records_names_the_process_behind_them(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
        params={"ids": "4471,4472,4473"},
    )

    text = response.text
    assert response.status_code == 200
    assert "ONLY IN AFFECTED" in text
    assert "SCHEDULED" in text
    assert "3 of 3 affected records" in text
    assert "0 of 3 others" in text


async def test_what_the_broken_records_skipped_is_surfaced_too(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # None of 4471-4473 went through the approval workflow that all three
    # others did. That absence is as much an answer as the shared change.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
        params={"ids": "4471 4472 4473"},
    )

    assert "ABSENT FROM AFFECTED" in response.text
    assert "Approval" in response.text


async def test_the_symptom_can_be_described_by_a_shared_value_instead(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # A consultant rarely has a list of IDs to hand; they have "the ones that
    # landed in 4010". Both routes must reach the same answer.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
        params={"field": "Account", "value": "4010"},
    )

    assert response.status_code == 200
    assert "ONLY IN AFFECTED" in response.text
    assert "SCHEDULED" in response.text


async def test_the_page_states_the_comparison_it_made(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
        params={"ids": "4471,4472,4473"},
    )

    assert "Comparing 3 affected records against 3 others" in response.text
    assert "not proof of a cause" in response.text


async def test_an_unmatched_description_says_so_rather_than_showing_nothing(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
        params={"ids": "999999"},
    )

    assert "No records matched" in response.text


async def test_the_form_alone_makes_no_claims(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate")

    assert response.status_code == 200
    assert "which records are wrong" in response.text
    assert "ONLY IN AFFECTED" not in response.text


async def test_the_deep_dive_offers_the_stronger_path(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    assert f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate" in response.text
    assert "several of them are wrong" in response.text


async def test_investigating_another_tenants_analysis_is_refused(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(
        client, db_session, "consultant-a@example.com", "Acme Corp"
    )
    analysis_id = await _upload(client, str(tenant_id))
    await logout(client)
    await login_as(client, db_session, "consultant-b@example.com")

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
        params={"ids": "4471"},
    )

    assert response.status_code == 403
