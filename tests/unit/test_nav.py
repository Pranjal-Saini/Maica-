import uuid

from maica.web.nav import NEEDS_ANALYSIS, NEEDS_RECORD, NEEDS_TENANT, build_nav

TENANT_ID = uuid.uuid4()
ANALYSIS_ID = uuid.uuid4()


def _by_key(items: list) -> dict:
    return {item.key: item for item in items}


def test_only_client_accounts_is_reachable_without_a_tenant() -> None:
    items = _by_key(build_nav())

    assert items["accounts"].href == "/dashboard"
    for key in ("analyses", "evidence", "deep_dive", "factors"):
        assert items[key].href is None
        assert items[key].is_enabled is False


def test_disabled_items_say_what_is_missing() -> None:
    # The sidebar takes the same posture as a report: name the blind spot
    # rather than rendering a link that goes nowhere.
    items = _by_key(build_nav())
    assert items["analyses"].disabled_reason == NEEDS_TENANT

    with_tenant = _by_key(build_nav(tenant_id=TENANT_ID))
    assert with_tenant["deep_dive"].disabled_reason == NEEDS_ANALYSIS

    with_analysis = _by_key(build_nav(tenant_id=TENANT_ID, analysis_id=ANALYSIS_ID))
    assert with_analysis["factors"].disabled_reason == NEEDS_RECORD


def test_tenant_context_unlocks_analyses_and_evidence() -> None:
    items = _by_key(build_nav(tenant_id=TENANT_ID))

    assert items["analyses"].href == f"/tenants/{TENANT_ID}/analyses"
    assert items["evidence"].href == f"/tenants/{TENANT_ID}/uploads/new"
    assert items["deep_dive"].href is None


def test_full_context_unlocks_every_item() -> None:
    items = _by_key(
        build_nav(tenant_id=TENANT_ID, analysis_id=ANALYSIS_ID, source_id="1001", tenant_count=2)
    )

    assert all(item.is_enabled for item in items.values())
    assert items["deep_dive"].href == f"/tenants/{TENANT_ID}/analyses/{ANALYSIS_ID}/records"
    assert (
        items["factors"].href == f"/tenants/{TENANT_ID}/analyses/{ANALYSIS_ID}/records/1001/report"
    )


def test_account_badge_counts_tenants_and_hides_at_zero() -> None:
    assert _by_key(build_nav(tenant_count=3))["accounts"].badge == "3"
    assert _by_key(build_nav(tenant_count=0))["accounts"].badge is None
    assert _by_key(build_nav())["accounts"].badge is None
