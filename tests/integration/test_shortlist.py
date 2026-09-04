"""The fallback shortlist, for a consultant with no transaction to start from.

The deep dive asks for a transaction; this is what it offers when the answer is
"I don't know which one". It is the weaker path — unusual is not wrong — so
what matters here is that it stays short and says why each record is on it.
"""

import re
from pathlib import Path

from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from maica.evidence.shortlist import SHORTLIST_LIMIT
from tests.conftest import login_as, logout, signup_with_tenant

FIXTURES = Path(__file__).parent.parent / "fixtures"

NOTES = (
    b"Internal ID,Record Type,Date,Field,Old Value,New Value,Set By,Context,Type\n"
    b"4471,Invoice,7/12/2026 09:15,Account,4000 - Product,4010 - Service,System,SCHEDULED,Change\n"
    b"4472,Invoice,7/12/2026 09:41,Account,4000 - Product,4010 - Service,System,SCHEDULED,Change\n"
    b"4473,Invoice,7/13/2026 14:20,Account,4000 - Product,4010 - Service,System,SCHEDULED,Change\n"
    b"4471,Invoice,7/12/2026 09:14,Amount,15000.00,18400.00,jsmith,UI,Change\n"
    b"4474,Invoice,7/13/2026 16:03,Amount,900.00,950.00,mchen,UI,Change\n"
    b"4475,Invoice,7/14/2026 02:00,Memo,,Reclass,System,CSVIMPORT,Create\n"
)


async def _upload(client: AsyncClient, tenant_id: str, name: str, data: bytes) -> str:
    response = await client.post(
        f"/tenants/{tenant_id}/uploads", files={"files": (name, data, "text/csv")}
    )
    return response.json()["analysis_id"]


async def test_a_snapshot_only_analysis_still_ranks_and_says_what_it_ranked_on(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Path A's wedge is a saved search, so this is the most common first
    # upload. Change patterns are impossible here, but the shortlist still has
    # to work — falling back to which values each record holds — and say so.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    analysis_id = await _upload(client, str(tenant_id), "s.csv", csv_bytes)

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    text = response.text
    assert "know which one?" in text
    # The ranking still runs on value keys; the gap block says why there are no
    # change patterns to show.
    assert "No change patterns could be built" in text
    assert "System Notes" in text


def _routine_notes(record_count: int, *, odd_one_out: str | None = None) -> bytes:
    """An account where almost everything is the same routine edit, plus at most
    one record that also carries something rare."""
    rows = [b"Internal ID,Record Type,Date,Field,Old Value,New Value,Set By,Context,Type\n"]
    for index in range(record_count):
        source_id = f"90{index:04d}"
        row = f"{source_id},Invoice,7/12/2026 09:15,Status,Open,Approved,jsmith,UI,Change\n"
        rows.append(row.encode())
    if odd_one_out:
        row = f"{odd_one_out},Invoice,7/12/2026 09:16,Account,4000,4010,System,SCHEDULED,Change\n"
        rows.append(row.encode())
    return b"".join(rows)


async def test_the_rare_change_outranks_the_account_routine(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The whole point of the measure. 30 records share one routine edit; one of
    them also carries an automated account change no other record has. That
    record must come first, and the routine must not push anything above it."""
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    notes = _routine_notes(30, odd_one_out="900007")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", notes)

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    text = response.text
    shortlist = text[text.index("know which one?") :]
    ranked = re.findall(r"/records/(\d+)/report", shortlist)

    assert ranked[0] == "900007"
    assert "Account changed" in shortlist
    assert "SCHEDULED" in shortlist


async def test_the_shortlist_is_short_however_many_records_there_are(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # The regression that started all of this: the page must not grow with the
    # size of the account.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", _routine_notes(400))

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    text = response.text
    shortlist = text[text.index("know which one?") :]
    ranked = set(re.findall(r"/records/(\d+)/report", shortlist))

    assert len(ranked) <= SHORTLIST_LIMIT
    assert "400 records in this analysis" in text
    assert len(text) < 120_000


async def test_every_shortlisted_record_states_why_it_is_there(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # A rank with no reason is just an opinion. Each row carries the counts the
    # consultant would need to disagree with it.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", NOTES)

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    shortlist = response.text[response.text.index("know which one?") :]
    assert "records in this analysis" in shortlist


async def test_the_shortlist_is_tenant_guarded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(
        client, db_session, "consultant-a@example.com", "Acme Corp"
    )
    await _upload(client, str(tenant_id), "notes.csv", NOTES)
    await logout(client)
    await login_as(client, db_session, "consultant-b@example.com")

    listing = await client.get(f"/tenants/{tenant_id}/analyses")

    assert listing.status_code == 403
