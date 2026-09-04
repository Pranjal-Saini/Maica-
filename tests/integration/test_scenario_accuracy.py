"""Accuracy against scenarios with a planted, known answer.

test-dataset/scenarios/ carries six datasets where the difference between the
affected records and the rest was put there on purpose, and ground_truth.json
records what it was. These tests assert the engine finds it — which makes
accuracy a number that cannot silently regress rather than something to be
re-measured by hand.

The scenario that plants nothing is the one to protect hardest. A diagnostic
that always finds something is worse than one that finds nothing, because the
consultant cannot tell the two apart.
"""

import json
import re
from pathlib import Path

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from tests.conftest import signup_with_tenant

SCENARIOS = Path(__file__).parent.parent.parent / "test-dataset" / "scenarios"
TRUTH = json.loads((SCENARIOS / "ground_truth.json").read_text(encoding="utf-8"))


def _findings(html: str) -> list[tuple[str, str]]:
    labels = re.findall(
        r"font-semibold tracking-wide\s*[^>]*>\s*([A-Z][A-Z ]+?)\s*</span>", html, re.S
    )
    described = re.findall(r'<p class="mt-3 leading-relaxed">\s*(.*?)\s*</p>', html, re.S)
    pairs = zip(labels, described, strict=False)
    return [(label, re.sub(r"\s+", " ", text)) for label, text in pairs]


async def _investigate(client: AsyncClient, tenant_id: str, name: str) -> str:
    expected = TRUTH[name]
    analysis_id = (
        await client.post(
            f"/tenants/{tenant_id}/uploads",
            files={"files": (f"{name}.csv", (SCENARIOS / f"{name}.csv").read_bytes(), "text/csv")},
        )
    ).json()["analysis_id"]
    response = await client.get(
        f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
        params={"ids": ",".join(expected["affected_ids"])},
    )
    assert response.status_code == 200
    return response.text


@pytest.mark.parametrize(
    "name",
    ["clean_automated_cause", "skipped_approval", "partial_cause", "confounded"],
)
async def test_the_planted_cause_is_the_top_finding(
    name: str, client: AsyncClient, db_session: AsyncSession
) -> None:
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    html = await _investigate(client, str(tenant_id), name)
    found = _findings(html)
    expected = TRUTH[name]

    assert found, f"{name}: nothing ranked, expected {expected['expect']}"
    label, described = found[0]
    assert label == expected["expect"], f"{name}: {expected['why']}"
    assert expected["field"] in described


async def test_a_confounder_on_every_record_does_not_win(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # Status was planted on all 300 records in both cohorts. It separates
    # nothing, so it must not be ranked at all — not merely ranked lower.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    html = await _investigate(client, str(tenant_id), "confounded")

    assert all("Status" not in described for _, described in _findings(html))


async def test_nothing_is_invented_when_the_cohorts_are_alike(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    """The false-positive test. Both cohorts were drawn from one distribution,
    so the honest answer is that nothing separates them."""
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    html = await _investigate(client, str(tenant_id), "nothing_to_find")

    assert _findings(html) == []
    assert "Nothing in this evidence separates" in html


async def test_two_affected_records_are_not_enough_to_conclude_from(
    client: AsyncClient, db_session: AsyncSession
) -> None:
    # A perfect separator on two records. Reporting that as a finding would be
    # the tool overreaching on almost no evidence.
    tenant_id = await signup_with_tenant(client, db_session, "consultant@example.com", "Acme Corp")

    html = await _investigate(client, str(tenant_id), "too_few_affected")

    assert _findings(html)[0][0] == "TOO FEW RECORDS TO TELL"
    assert "could as easily be coincidence" in html
