"""The deep dive as a pattern index.

The regression that matters most here is that the count printed on a pattern
card equals the number of records behind it. The card comes from a GROUP BY and
the drill-down from a WHERE; if those two expressions ever drift apart the page
lies quietly, which is worse than being slow.
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


async def test_the_index_groups_changes_by_field_and_actor(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", NOTES)

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    text = response.text
    assert response.status_code == 200
    assert "Account" in text and "Amount" in text
    # Three records had Account changed by System via SCHEDULED.
    assert "SCHEDULED" in text
    assert "not a specific person" in text
    assert "5 records · 3 fields changed" in text


async def test_a_first_population_is_not_grouped_with_modifications(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Record 4475's Memo went from empty to a value. Calling that a change
    # alongside genuine modifications mislabels it — rules.py already draws
    # this line for factors.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", NOTES)

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    assert "first set" in response.text
    assert "modified" in response.text


async def test_a_card_count_equals_the_records_behind_it(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The aggregate and the drill-down predicate are built from the same SQL
    expressions precisely so this holds. If it ever fails they have drifted."""
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", NOTES)

    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/patterns/records",
        params={
            "field": "Account",
            "change_kind": "modified",
            "actor_class": "System",
            "context": "SCHEDULED",
        },
    )

    text = response.text
    assert response.status_code == 200
    assert "of 3 records" in text
    for source_id in ("4471", "4472", "4473"):
        assert f"/records/{source_id}/report" in text
    # 4474's Amount change is a different pattern and must not leak in.
    assert "/records/4474/report" not in text


async def test_a_pattern_with_no_context_is_still_reachable(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # context is nullable, so its absence travels as a flag. A magic string
    # would collide with a context genuinely named the same thing.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    no_context = (
        b"Internal ID,Record Type,Date,Field,Old Value,New Value,Set By,Type\n"
        b"5001,Invoice,7/12/2026 09:15,Account,4000,4010,jsmith,Change\n"
    )
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", no_context)

    index = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")
    drill = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/patterns/records",
        params={
            "field": "Account",
            "change_kind": "modified",
            "actor_class": "user",
            "context_missing": 1,
        },
    )

    assert "context_missing=1" in index.text
    assert drill.status_code == 200
    assert "of 1 record" in drill.text
    assert "/records/5001/report" in drill.text


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
    assert "Start here" in text
    # The ranking still runs on value keys; the gap block says why there are no
    # change patterns to show.
    assert "No change patterns could be built" in text
    assert "System Notes" in text


async def test_a_part_snapshot_analysis_states_its_coverage(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    csv_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    analysis_id = await _upload(client, str(tenant_id), "s.csv", csv_bytes)
    await client.post(
        f"/tenants/{tenant_id}/uploads",
        data={"analysis_id": analysis_id},
        files={"files": ("notes.csv", NOTES, "text/csv")},
    )

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    assert "have change evidence" in response.text
    assert "appear only in snapshot evidence" in response.text


async def test_sorting_smallest_first_reaches_the_rare_pattern(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", NOTES)

    largest = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records?sort=largest")
    smallest = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/records?sort=smallest"
    )

    assert largest.status_code == 200 and smallest.status_code == 200
    # Scoped to the accordion: the shortlist above it names fields too, so a
    # whole-document string search would compare the wrong occurrences.
    marker = "All change patterns"
    largest_accordion = largest.text[largest.text.index(marker) :]
    smallest_accordion = smallest.text[smallest.text.index(marker) :]
    assert largest_accordion.index("Account") < largest_accordion.index("Memo")
    assert smallest_accordion.index("Memo") < smallest_accordion.index("Account")


async def test_the_drill_down_is_tenant_guarded(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(
        client, db_session, "consultant-a@example.com", "Acme Corp"
    )
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", NOTES)
    await logout(client)
    await login_as(client, db_session, "consultant-b@example.com")

    index = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")
    drill = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/patterns/records",
        params={
            "field": "Account",
            "change_kind": "modified",
            "actor_class": "System",
            "context": "SCHEDULED",
        },
    )

    assert index.status_code == 403
    assert drill.status_code == 403


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
    shortlist = text[text.index("Start here") : text.index("All change patterns")]
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
    shortlist = text[text.index("Start here") : text.index("All change patterns")]
    ranked = set(re.findall(r"/records/(\d+)/report", shortlist))

    assert len(ranked) <= SHORTLIST_LIMIT
    assert "400 records" in text  # the total is still stated
    assert len(text) < 120_000


async def test_every_shortlisted_record_states_why_it_is_there(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # A rank with no reason is just an opinion. Each row carries the counts the
    # consultant would need to disagree with it.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")
    analysis_id = await _upload(client, str(tenant_id), "notes.csv", NOTES)

    response = await client.get(f"/tenants/{tenant_id}/analyses/{analysis_id}/records")

    shortlist = response.text[response.text.index("Start here") :]
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
