"""The engine's resilience settings.

Postgres restarting is a normal event — a service restart, a managed-database
maintenance window, an idle timeout. It must not turn into an outage that only
a redeploy clears.
"""

from maica.evidence.db import get_engine


def test_the_pool_checks_a_connection_is_alive_before_handing_it_out() -> None:
    # Without this, every request after a database restart fails on a dead
    # pooled connection until the app process itself is restarted.
    assert get_engine().pool._pre_ping is True
