"""Optional MySQL checks; set MYSQL_INTEGRATION_URL, then run this module.

Use a migrated local database and a mysql+pymysql URL from the environment.
All data is synthetic (reference date: 2026-09-09), not live travel evidence.
Each test rolls back its own UUID-scoped rows and never changes the schema.
"""

import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest

if not os.environ.get("MYSQL_INTEGRATION_URL"):
    pytest.skip("Set MYSQL_INTEGRATION_URL to run real MySQL checks", allow_module_level=True)

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.exc import DBAPIError

from app.models import AgentRun, PlanningTask, Trip, TripVersion

TRIPS = Trip.__table__
TASKS = PlanningTask.__table__
AGENTS = AgentRun.__table__
VERSIONS = TripVersion.__table__
REFERENCE_TIME = datetime(2026, 9, 9, 4, 0)


@pytest.fixture
def mysql_connection():
    # The driver is loaded only after the explicit opt-in above.
    url = make_url(os.environ["MYSQL_INTEGRATION_URL"])
    assert url.drivername == "mysql+pymysql", "Use a mysql+pymysql integration URL"
    engine = create_engine(
        url, hide_parameters=True, connect_args={"connect_timeout": 3}
    )
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                yield connection
            finally:
                transaction.rollback()
    finally:
        engine.dispose()


def insert_trip(connection):
    trip_id = str(uuid4())
    connection.execute(TRIPS.insert().values(
        id=trip_id,
        destination="杭州 🧭",
        start_date=date(2026, 9, 10),
        end_date=date(2026, 9, 12),
        travelers=3,
        budget_total=Decimal("6000.10"),
        request_json={"preferences": ["西湖", "运河 🚣"], "fixture": True},
        current_version=None,
        created_at=REFERENCE_TIME,
    ))
    return trip_id


def insert_chain(connection):
    trip_id = insert_trip(connection)
    task_id, agent_id = str(uuid4()), str(uuid4())
    connection.execute(TASKS.insert().values(
        id=task_id,
        trip_id=trip_id,
        deadline_at=REFERENCE_TIME + timedelta(minutes=2),
        created_at=REFERENCE_TIME,
    ))
    connection.execute(AGENTS.insert().values(
        id=agent_id,
        task_id=task_id,
        agent_name="FixturePlanner",
        summary={"text": "杭州行程 🧭", "fixture": True},
        evidence_refs=[{"source": "synthetic fixture", "reference_time": "2026-09-09"}],
        created_at=REFERENCE_TIME,
    ))
    connection.execute(VERSIONS.insert().values(
        trip_id=trip_id,
        version=1,
        parent_version=None,
        plan_json={"days": [{"name": "西湖漫步 🚶"}], "fixture": True},
        validation_json={"fixture": True, "warnings": []},
        budget_json={"total": "6000.10", "currency": "CNY"},
        created_at=REFERENCE_TIME,
    ))
    # Core executes immediately: the snapshot exists before this FK is assigned.
    connection.execute(
        TRIPS.update().where(TRIPS.c.id == trip_id).values(current_version=1)
    )
    return trip_id, task_id, agent_id


def test_mysql_roundtrip_unicode_money_and_current_snapshot(mysql_connection):
    connection = mysql_connection
    trip_id, task_id, agent_id = insert_chain(connection)
    trip = connection.execute(select(TRIPS).where(TRIPS.c.id == trip_id)).mappings().one()
    task = connection.execute(select(TASKS).where(TASKS.c.id == task_id)).mappings().one()
    agent = connection.execute(select(AGENTS).where(AGENTS.c.id == agent_id)).mappings().one()
    version = connection.execute(select(VERSIONS).where(
        VERSIONS.c.trip_id == trip_id, VERSIONS.c.version == trip["current_version"]
    )).mappings().one()

    assert trip["destination"] == "杭州 🧭"
    assert trip["request_json"]["preferences"] == ["西湖", "运河 🚣"]
    assert trip["budget_total"] == Decimal("6000.10")
    assert isinstance(trip["budget_total"], Decimal)
    assert trip["budget_total"].as_tuple().exponent == -2
    assert trip["created_at"] == REFERENCE_TIME
    assert trip["currency"] == "CNY"
    assert trip["budget_scope"] == "destination_only"
    assert task["trip_id"] == trip_id
    assert agent["task_id"] == task_id
    assert agent["summary"]["text"] == "杭州行程 🧭"
    assert agent["evidence_refs"][0]["source"] == "synthetic fixture"
    assert trip["current_version"] == version["version"] == 1
    assert version["plan_json"]["days"][0]["name"] == "西湖漫步 🚶"
    assert version["budget_json"]["total"] == "6000.10"


def test_mysql_rejects_invalid_constraints_and_cross_trip_snapshot(mysql_connection):
    connection = mysql_connection
    trip_id, _, _ = insert_chain(connection)
    other_trip_id = insert_trip(connection)
    cases = [
        (TRIPS.update().where(TRIPS.c.id == trip_id).values(travelers=0), 3819),
        (TRIPS.update().where(TRIPS.c.id == trip_id).values(budget_total=Decimal("0")), 3819),
        (VERSIONS.insert().values(
            trip_id=trip_id, version=2, parent_version=2,
            plan_json={}, validation_json={}, budget_json={}, created_at=REFERENCE_TIME,
        ), 3819),
        (TASKS.insert().values(
            id=str(uuid4()), trip_id=str(uuid4()),
            deadline_at=REFERENCE_TIME + timedelta(minutes=2), created_at=REFERENCE_TIME,
        ), 1452),
        # Version 1 exists for the first trip, but not for this trip.
        (TRIPS.update().where(TRIPS.c.id == other_trip_id).values(current_version=1), 1452),
    ]
    for statement, expected_mysql_code in cases:
        with pytest.raises(DBAPIError) as caught:
            with connection.begin_nested():
                connection.execute(statement)
        assert caught.value.orig.args[0] == expected_mysql_code

    # Failed statements must not poison or partially alter the outer transaction.
    trip = connection.execute(select(TRIPS).where(TRIPS.c.id == trip_id)).mappings().one()
    assert trip["travelers"] == 3
    assert trip["budget_total"] == Decimal("6000.10")
    assert connection.scalar(select(TRIPS.c.current_version).where(
        TRIPS.c.id == other_trip_id
    )) is None


def test_mysql_clear_current_snapshot_then_delete_cascades(mysql_connection):
    connection = mysql_connection
    trip_id, task_id, agent_id = insert_chain(connection)
    own_rows = [
        (TRIPS, TRIPS.c.id == trip_id),
        (TASKS, TASKS.c.id == task_id),
        (AGENTS, AGENTS.c.id == agent_id),
        (VERSIONS, VERSIONS.c.trip_id == trip_id),
    ]
    for table, predicate in own_rows:
        assert connection.execute(select(table).where(predicate)).first() is not None

    connection.execute(
        TRIPS.update().where(TRIPS.c.id == trip_id).values(current_version=None)
    )
    connection.execute(TRIPS.delete().where(TRIPS.c.id == trip_id))

    for table, predicate in own_rows:
        assert connection.execute(select(table).where(predicate)).first() is None
