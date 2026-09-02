import uuid

from maica.web.nav import (
    NEED_ACCOUNT,
    NEED_ANALYSIS,
    NEED_RECORD,
    NavContext,
    build_nav,
)

TENANT_ID = "11111111-1111-1111-1111-111111111111"
ANALYSIS_ID = "22222222-2222-2222-2222-222222222222"


def _by_key(context: NavContext, **kwargs: object) -> dict:
    return {item.key: item for item in build_nav(context, **kwargs)}  # type: ignore[arg-type]


def test_every_row_is_clickable_even_with_no_context() -> None:
    # The sidebar must never render a dead row: with nothing remembered,
    # each one still leads to the page where that context gets picked.
    items = _by_key(NavContext())

    assert all(item.href for item in items.values())
    assert items["accounts"].href == "/dashboard"
    for key in ("analyses", "evidence", "deep_dive", "factors"):
        assert items[key].href == f"/dashboard?need={NEED_ACCOUNT}"
        assert items[key].needs == NEED_ACCOUNT


def test_a_remembered_tenant_unlocks_analyses_and_evidence() -> None:
    items = _by_key(NavContext(tenant_id=TENANT_ID))

    assert items["analyses"].href == f"/tenants/{TENANT_ID}/analyses"
    assert items["analyses"].needs is None
    assert items["evidence"].href == f"/tenants/{TENANT_ID}/uploads/new"
    # Deeper rows fall back to the analyses list, which can say what to pick.
    assert items["deep_dive"].href == f"/tenants/{TENANT_ID}/analyses?need={NEED_ANALYSIS}"
    assert items["deep_dive"].needs == NEED_ANALYSIS


def test_a_remembered_analysis_unlocks_deep_dive_and_points_factors_at_records() -> None:
    items = _by_key(NavContext(tenant_id=TENANT_ID, analysis_id=ANALYSIS_ID))

    records = f"/tenants/{TENANT_ID}/analyses/{ANALYSIS_ID}/records"
    assert items["deep_dive"].href == records
    assert items["factors"].href == f"{records}?need={NEED_RECORD}"
    assert items["factors"].needs == NEED_RECORD


def test_full_context_points_every_row_at_real_data() -> None:
    items = _by_key(
        NavContext(tenant_id=TENANT_ID, analysis_id=ANALYSIS_ID, source_id="1001"),
        tenant_count=2,
    )

    assert all(item.needs is None for item in items.values())
    assert (
        items["factors"].href == f"/tenants/{TENANT_ID}/analyses/{ANALYSIS_ID}/records/1001/report"
    )


def test_a_record_without_its_analysis_is_ignored() -> None:
    # Guards against a stale source_id surviving a tenant switch and producing
    # a link into an analysis the consultant is no longer in.
    items = _by_key(NavContext(tenant_id=TENANT_ID, source_id="1001"))

    assert items["factors"].needs == NEED_ANALYSIS
    assert "1001" not in items["factors"].href


def test_account_badge_counts_tenants_and_hides_at_zero() -> None:
    assert _by_key(NavContext(), tenant_count=3)["accounts"].badge == "3"
    assert _by_key(NavContext(), tenant_count=0)["accounts"].badge is None
    assert _by_key(NavContext())["accounts"].badge is None


class _FakeRequest:
    """remember_context only touches request.session."""

    def __init__(self, session: dict | None = None) -> None:
        self.session = session if session is not None else {}


def test_remember_context_survives_a_page_without_that_context() -> None:
    from maica.web.nav import remember_context

    request = _FakeRequest()
    remember_context(
        request,
        tenant_id=uuid.UUID(TENANT_ID),
        analysis_id=uuid.UUID(ANALYSIS_ID),
        source_id="1001",
    )

    # The dashboard carries no tenant at all — the sidebar must still be able
    # to link back to where the consultant was.
    carried = remember_context(request)

    assert carried.tenant_id == TENANT_ID
    assert carried.analysis_id == ANALYSIS_ID
    assert carried.source_id == "1001"


def test_switching_tenant_drops_the_analysis_and_record_below_it() -> None:
    from maica.web.nav import remember_context

    request = _FakeRequest()
    remember_context(
        request,
        tenant_id=uuid.UUID(TENANT_ID),
        analysis_id=uuid.UUID(ANALYSIS_ID),
        source_id="1001",
    )

    other_tenant = uuid.uuid4()
    switched = remember_context(request, tenant_id=other_tenant)

    assert switched.tenant_id == str(other_tenant)
    assert switched.analysis_id is None
    assert switched.source_id is None


def test_switching_analysis_drops_the_remembered_record() -> None:
    from maica.web.nav import remember_context

    request = _FakeRequest()
    remember_context(
        request,
        tenant_id=uuid.UUID(TENANT_ID),
        analysis_id=uuid.UUID(ANALYSIS_ID),
        source_id="1001",
    )

    other_analysis = uuid.uuid4()
    switched = remember_context(request, analysis_id=other_analysis)

    assert switched.tenant_id == TENANT_ID
    assert switched.analysis_id == str(other_analysis)
    assert switched.source_id is None
