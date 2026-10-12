from datetime import datetime, timedelta, timezone

import pytest
from conftest import FakeLLM, FakeRetriever

from app.pipeline.orchestrator import Orchestrator
from app.pipeline.responder import Responder
from app.state.session_store import MIGRATIONS, InMemorySessionStore, SqliteSessionStore


class Clock:
    def __init__(self):
        self.now = datetime(2026, 10, 1, tzinfo=timezone.utc)

    def __call__(self):
        return self.now


@pytest.fixture(params=["memory", "sqlite"])
def make_store(request, tmp_path):
    def make(clock=None):
        clock = clock or Clock()
        if request.param == "memory":
            return InMemorySessionStore(retention_days=7, clock=clock)
        return SqliteSessionStore(tmp_path / "state.db", retention_days=7, clock=clock)
    return make


def test_round_trip_keeps_every_field(make_store):
    store = make_store()
    session = store.create("fr")
    session.urgency_level = 5
    session.symptoms = ["chest_pain"]
    session.history = [{"role": "user", "content": "J'ai mal à la poitrine"}]
    session.asked_questions = [("pain", 0), ("duration", 0)]
    store.save(session)

    loaded = store.get(session.session_id)
    assert (loaded.language, loaded.urgency_level, loaded.symptoms) == ("fr", 5, ["chest_pain"])
    assert loaded.history == [{"role": "user", "content": "J'ai mal à la poitrine"}]
    assert loaded.asked_questions == [("pain", 0), ("duration", 0)]  # tuples, as the pipeline expects


def test_unknown_session_is_none(make_store):
    assert make_store().get("does-not-exist") is None


def test_sessions_past_retention_are_deleted(make_store):
    clock = Clock()
    store = make_store(clock)
    old, recent = store.create("en"), None
    clock.now += timedelta(days=6)
    recent = store.create("en")
    clock.now += timedelta(days=2)  # old: 8 days without activity, recent: 2 days
    assert store.delete_expired() == 1
    assert store.get(old.session_id) is None and store.get(recent.session_id) is not None


def test_activity_resets_the_retention_clock(make_store):
    clock = Clock()
    store = make_store(clock)
    session = store.create("en")
    clock.now += timedelta(days=6)
    store.save(session)  # a new message
    clock.now += timedelta(days=6)
    assert store.delete_expired() == 0


def test_sqlite_sessions_survive_a_restart(tmp_path):
    first = SqliteSessionStore(tmp_path / "state.db", retention_days=7)
    session = first.create("fr")
    session.urgency_level = 4
    first.save(session)
    first.close()

    restarted = SqliteSessionStore(tmp_path / "state.db", retention_days=7)
    assert restarted.get(session.session_id).urgency_level == 4


def test_migrations_bring_a_new_database_to_the_latest_schema(tmp_path):
    store = SqliteSessionStore(tmp_path / "state.db", retention_days=7)
    assert store.schema_version == len(MIGRATIONS)
    store.close()
    assert SqliteSessionStore(tmp_path / "state.db", retention_days=7).schema_version == len(MIGRATIONS)


def test_conversation_continues_after_a_server_restart(tmp_path):
    def server():
        store = SqliteSessionStore(tmp_path / "state.db", retention_days=7)
        return Orchestrator(Responder(FakeRetriever(), FakeLLM()), store=store), store

    orchestrator, store = server()
    first = orchestrator.handle("I took an overdose", language="en")
    store.close()

    orchestrator, _ = server()  # "restart": new process state, same database
    second = orchestrator.handle("I also have a mild cough", session_id=first.session_id)
    assert second.session_id == first.session_id
    assert second.urgency_level == 5  # urgency never goes down, even across restarts
    assert len(orchestrator.get_session(first.session_id).history) == 4
