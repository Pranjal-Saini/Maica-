from pathlib import Path

from httpx import AsyncClient

FIXTURES = Path(__file__).parent.parent / "fixtures"
TENANT_ID = "12121212-1212-1212-1212-121212121212"


async def test_uploading_system_notes_into_existing_analysis_combines_evidence(
    client: AsyncClient,
) -> None:
    saved_search_bytes = (FIXTURES / "saved_search_clean.csv").read_bytes()
    first_response = await client.post(
        "/uploads",
        data={"evidence_type": "saved_search_csv"},
        files={"file": ("saved_search_clean.csv", saved_search_bytes, "text/csv")},
        headers={"X-Tenant-Id": TENANT_ID},
    )
    analysis_id = first_response.json()["raw_evidence"]["analysis_id"]

    system_notes_bytes = (FIXTURES / "system_notes_clean.csv").read_bytes()
    second_response = await client.post(
        "/uploads",
        data={"evidence_type": "system_notes_csv", "analysis_id": analysis_id},
        files={"file": ("system_notes_clean.csv", system_notes_bytes, "text/csv")},
        headers={"X-Tenant-Id": TENANT_ID},
    )

    assert second_response.status_code == 200
    second_body = second_response.json()
    assert second_body["raw_evidence"]["analysis_id"] == analysis_id
    assert second_body["records_created"] == 3

    factors_response = await client.get(
        f"/analyses/{analysis_id}/records/1001/factors", headers={"X-Tenant-Id": TENANT_ID}
    )
    body = factors_response.json()

    # 1001 has 2 field-change factors (Amount, Status) from system notes, plus
    # the pre-existing shared-value factors from the saved-search upload.
    change_factors = [f for f in body["factors"] if "changed from" in f["summary"]]
    assert len(change_factors) == 2
    assert body["factors"][0] in change_factors  # change factors rank first
    assert not any(
        "No script, workflow, integration, or configuration-change evidence" in g["description"]
        for g in body["gaps"]
    )


async def test_upload_with_unknown_evidence_type_is_rejected(client: AsyncClient) -> None:
    response = await client.post(
        "/uploads",
        data={"evidence_type": "not_a_real_type"},
        files={"file": ("whatever.csv", b"a,b\n1,2\n", "text/csv")},
        headers={"X-Tenant-Id": TENANT_ID},
    )

    assert response.status_code == 422
    assert "not_a_real_type" in response.json()["error"]["message"]
