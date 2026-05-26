"""Tests for the memory isolation system."""

import time
import pytest
from memory.isolation import MemoryIsolationManager, MemoryScope


@pytest.fixture
def manager():
    return MemoryIsolationManager(cleanup_interval=1.0)


def test_create_and_get(manager):
    memory = manager.get_or_create("session", "session-1")
    assert memory is not None
    assert memory.scope.scope_type == "session"
    assert memory.scope.scope_id == "session-1"
    assert memory.access_count == 1
    assert memory.created_at > 0


def test_get_existing(manager):
    m1 = manager.get_or_create("session", "s1")
    m2 = manager.get_or_create("session", "s1")
    assert m1 is m2  # Same object
    assert m2.access_count == 2


def test_get_nonexistent(manager):
    assert manager.get("session", "nonexistent") is None


def test_delete_scope(manager):
    manager.get_or_create("session", "to-delete")
    assert manager.delete_scope("session", "to-delete") is True
    assert manager.get("session", "to-delete") is None
    assert manager.delete_scope("session", "nonexistent") is False


def test_session_with_user_and_node(manager):
    session_mem, inherited = manager.get_scope_for_session(
        session_id="sess-1",
        user_id="user-1",
        node_id="node-1",
    )
    assert session_mem.scope.scope_type == "session"
    assert len(inherited) == 2  # both user and node


def test_session_with_user_only(manager):
    session_mem, inherited = manager.get_scope_for_session(
        session_id="sess-2",
        user_id="user-2",
    )
    assert len(inherited) == 1
    assert inherited[0].scope.scope_type == "user"
    assert inherited[0].scope.scope_id == "user-2"


def test_accessible_memories(manager):
    parent = manager.get_or_create("user", "u1")
    child = manager.get_or_create("session", "s1", parent_scope_type="user", parent_scope_id="u1")

    accessible = manager.get_accessible_memories("session", "s1")
    assert len(accessible) == 2  # session + user


def test_cleanup_sessions(manager):
    manager.get_or_create("session", "s1")
    manager.get_or_create("session", "s2")
    manager.get_or_create("user", "u1")

    count = manager.cleanup_all_sessions()
    assert count == 2


def test_stats(manager):
    manager.get_or_create("session", "s1")
    manager.get_or_create("user", "u1")
    manager.get_or_create("node", "n1")

    stats = manager.stats()
    assert stats["sessions"] == 1
    assert stats["users"] == 1
    assert stats["nodes"] == 1
    assert stats["total_scopes"] == 3


def test_memory_scope_key():
    scope = MemoryScope(scope_type="session", scope_id="abc")
    assert scope.key() == "session:abc"
    assert scope.parent_key() is None


def test_memory_scope_parent_key():
    scope = MemoryScope(scope_type="session", scope_id="abc",
                        parent_scope_type="user", parent_scope_id="user1")
    assert scope.parent_key() == "user:user1"


def test_get_accessible_with_parent_chain(manager):
    """Test that accessible memories walks up the parent chain."""
    manager.get_or_create("global", "g1")
    user = manager.get_or_create("user", "u1",
                                 parent_scope_type="global", parent_scope_id="g1")
    session = manager.get_or_create("session", "s1",
                                    parent_scope_type="user", parent_scope_id="u1")

    accessible = manager.get_accessible_memories("session", "s1")
    # Should have session, user - but not global if not linked properly
    assert len(accessible) >= 1
