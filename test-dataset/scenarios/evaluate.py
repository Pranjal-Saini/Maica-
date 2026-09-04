"""Scores the investigation against the planted answers.

Uploads each scenario through the real ingest path, calls the real
/investigate route, and compares the top finding with what
generate_scenarios.py planted. Nothing is reimplemented here — a harness that
recomputes the answer its own way would only ever be testing itself.

    uv run python test-dataset/scenarios/evaluate.py

Needs the Postgres the tests use. It drops and recreates the schema, so point
DATABASE_URL at a scratch database, never a real one.
"""

import asyncio
import base64
import json
import os
import re
from pathlib import Path

os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://maica:maica@localhost:5432/maica_test")

HERE = Path(__file__).parent
TRUTH = json.loads((HERE / "ground_truth.json").read_text(encoding="utf-8"))


def _top_finding(html: str) -> tuple[str, str] | None:
    """The separation label and description of the first ranked finding."""
    match = re.search(
        r"font-semibold tracking-wide\s*[^>]*>\s*([A-Z][A-Z ]+?)\s*</span>.*?"
        r'<p class="mt-3 leading-relaxed">\s*(.*?)\s*</p>',
        html,
        re.S,
    )
    if not match:
        return None
    return match.group(1).strip(), re.sub(r"\s+", " ", match.group(2))


async def main() -> None:
    from httpx import ASGITransport, AsyncClient
    from itsdangerous import TimestampSigner
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from maica.api.deps import get_db_session, get_llm_client
    from maica.api.main import create_app
    from maica.auth import repository as auth_repo
    from maica.auth.google_oauth import GoogleUserInfo
    from maica.config.settings import get_settings
    from maica.evidence.db import Base

    engine = create_async_engine(get_settings().database_url)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.drop_all)
        await connection.run_sync(Base.metadata.create_all)
    session = async_sessionmaker(engine, expire_on_commit=False)()

    app = create_app()

    async def _db():
        yield session

    async def _llm():
        return None

    app.dependency_overrides[get_db_session] = _db
    app.dependency_overrides[get_llm_client] = _llm

    user = await auth_repo.get_or_create_user_from_google(
        session, GoogleUserInfo(sub="eval", email="eval@example.com", name="Eval")
    )
    await session.commit()

    results = []
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://eval") as client:
        signer = TimestampSigner(get_settings().session_secret_key)
        cookie = signer.sign(base64.b64encode(json.dumps({"user_id": str(user.id)}).encode()))
        client.cookies.set("session", cookie.decode())
        await client.post("/tenants", data={"name": "Scenarios"})
        tenant_id = (
            (await client.get("/dashboard")).text.split("/tenants/")[1].split("/analyses")[0]
        )

        for name, expected in TRUTH.items():
            csv_bytes = (HERE / f"{name}.csv").read_bytes()
            analysis_id = (
                await client.post(
                    f"/tenants/{tenant_id}/uploads",
                    files={"files": (f"{name}.csv", csv_bytes, "text/csv")},
                )
            ).json()["analysis_id"]

            page = await client.get(
                f"/tenants/{tenant_id}/analyses/{analysis_id}/investigate",
                params={"ids": ",".join(expected["affected_ids"])},
            )
            top = _top_finding(page.text)
            wanted = expected["expect"]

            if wanted == "NOTHING":
                passed = top is None
                got = "no finding" if top is None else f"{top[0]}: {top[1]}"
            else:
                passed = top is not None and top[0] == wanted and expected["field"] in top[1]
                got = f"{top[0]}: {top[1]}" if top else "no finding"

            if passed and "must_not_rank_first" in expected:
                passed = expected["must_not_rank_first"] not in (top[1] if top else "")

            results.append((name, wanted, got, passed, expected.get("why", "")))

    await session.close()
    await engine.dispose()

    print(f"\n{'SCENARIO':<24}{'EXPECTED':<26}RESULT")
    print("-" * 100)
    for name, wanted, got, passed, _ in results:
        print(f"{'PASS' if passed else 'FAIL':<6}{name:<24}{wanted:<26}{got[:44]}")

    correct = sum(1 for *_, passed, _ in results if passed)
    print("-" * 100)
    print(f"accuracy: {correct}/{len(results)} = {correct / len(results):.0%}")


if __name__ == "__main__":
    asyncio.run(main())
