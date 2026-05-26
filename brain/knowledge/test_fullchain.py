import os
import tempfile
import time
import pytest
from knowledge import SkillEngine, SkillStore, Skill, SkillTrigger, SkillAction, SkillVerification
from rag.engine import RAGEngine, MemoryVectorStore
from memory.isolation import MemoryIsolationManager


class MockEmbedder:
    def __init__(self):
        self._cache_hits = 0
        self._cache_misses = 0

    async def embed(self, text):
        import hashlib
        h = hashlib.md5(text.encode()).hexdigest()
        return [float(ord(c)) / 255.0 for c in h[:8]]

    async def embed_batch(self, texts):
        return [await self.embed(t) for t in texts]

    def cache_stats(self):
        return {"hits": self._cache_hits, "misses": self._cache_misses}


@pytest.fixture
def skills_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def skill_store(skills_dir):
    return SkillStore(skills_dir)


@pytest.fixture
def skill_engine(skill_store):
    return SkillEngine(skill_store)


@pytest.fixture
def rag_engine():
    embedder = MockEmbedder()
    store = MemoryVectorStore()
    return RAGEngine(embedder, store, chunk_size=200, chunk_overlap=20)


@pytest.fixture
def memory_manager():
    return MemoryIsolationManager()


@pytest.mark.asyncio
async def test_full_chain_alert_to_remediation(skill_engine, rag_engine, memory_manager):
    disk_skill = Skill(
        id="disk.cleanup.v1",
        name="Disk Space Cleanup",
        triggers=[SkillTrigger(metric="disk.usage", operator=">", threshold=85)],
        remediation_actions=[
            SkillAction(tool="exec.run", params={"command": "journalctl --vacuum-size=500M"})
        ],
        tags=["disk", "linux"],
    )
    skill_engine.store.save(disk_skill)

    await rag_engine.index_fault_record(
        fault_id="hist-001",
        alert={"action": "disk.usage", "severity": "critical"},
        diagnosis="/var/log filled with journal logs",
        resolution="journalctl --vacuum-size=500M followed by logrotate restart",
        tags=["disk", "cleanup"],
    )
    await rag_engine.index_fault_record(
        fault_id="hist-002",
        alert={"action": "port.check", "severity": "warning"},
        diagnosis="Port 443 timeout",
        resolution="Restart nginx service",
        tags=["network", "nginx"],
    )

    session_memory, inherited = memory_manager.get_scope_for_session(
        session_id="session-fullchain-1",
        user_id="admin",
        node_id="node-web-01",
    )
    assert session_memory is not None
    assert len(inherited) == 2

    alert = {
        "action": "disk.usage",
        "severity": "critical",
        "message": "Disk usage at 94% on /",
        "tags": ["disk", "linux"],
        "disk": {"usage": 94.0},
        "node": "node-web-01",
    }

    best_skill = skill_engine.find_best_skill(alert)
    assert best_skill is not None
    assert best_skill.id == "disk.cleanup.v1"
    assert best_skill.matches_alert(alert) > 0.5

    rag_results = await rag_engine.query("disk space cleanup", top_k=3)
    assert rag_results.total_found > 0
    has_disk_context = any("journal" in doc.content for doc in rag_results.documents)
    assert has_disk_context, "RAG should return disk-related historical context"

    assert session_memory.scope.key() == "session:session-fullchain-1"
    assert session_memory.scope.parent_scope_type == "user"
    assert session_memory.scope.parent_scope_id == "admin"

    actions = best_skill.remediation_actions
    assert len(actions) == 1
    assert actions[0].tool == "exec.run"

    best_skill.record_result(success=True)
    skill_engine.store.save(best_skill)

    updated = skill_engine.store.get("disk.cleanup.v1")
    assert updated is not None
    assert updated.total_attempts == 1
    assert updated.total_successes == 1
    assert updated.success_rate == 1.0


@pytest.mark.asyncio
async def test_full_chain_no_skill_match(skill_engine, rag_engine, memory_manager):
    unknown_alert = {
        "action": "unknown.custom",
        "severity": "critical",
        "message": "Unknown failure mode",
        "tags": ["custom"],
        "unknown": {"param": 99},
    }
    best_skill = skill_engine.find_best_skill(unknown_alert)
    assert best_skill is None

    rag_results = await rag_engine.query("unknown failure mode", top_k=3)
    assert rag_results is not None


@pytest.mark.asyncio
async def test_full_chain_skill_with_rollback(skill_engine, rag_engine, memory_manager):
    nginx_skill = Skill(
        id="nginx.restart.v1",
        name="Nginx Service Restart",
        triggers=[SkillTrigger(metric="http.status", operator="!=", threshold=200)],
        remediation_actions=[
            SkillAction(tool="service.status", params={"name": "nginx"})
        ],
        rollback_plan=[
            SkillAction(tool="exec.run", params={"command": "systemctl start nginx"})
        ],
        verification=SkillVerification(tool="http.health", params={"url": "http://localhost"}),
        tags=["nginx", "web"],
    )
    skill_engine.store.save(nginx_skill)

    alert = {
        "action": "http.health",
        "severity": "critical",
        "message": "Nginx 503 error",
        "tags": ["nginx", "web"],
        "http": {"status": 503},
    }
    best = skill_engine.find_best_skill(alert)
    assert best is not None
    assert best.id == "nginx.restart.v1"
    assert len(best.rollback_plan) == 1
    assert "start nginx" in str(best.rollback_plan[0].params.get("command", ""))


@pytest.mark.asyncio
async def test_full_chain_memory_isolation_no_cross_contamination(skill_engine, rag_engine, memory_manager):
    session1, inherited1 = memory_manager.get_scope_for_session(
        session_id="session-a", user_id="user-alpha", node_id="node-db-01",
    )
    session2, inherited2 = memory_manager.get_scope_for_session(
        session_id="session-b", user_id="user-beta", node_id="node-web-02",
    )

    assert session1.scope.key() == "session:session-a"
    assert session2.scope.key() == "session:session-b"
    assert session1.scope.key() != session2.scope.key()

    assert inherited1[0].scope.key() == "user:user-alpha"
    assert inherited2[0].scope.key() == "user:user-beta"
    assert inherited1[0].scope.key() != inherited2[0].scope.key()

    session1_again, _ = memory_manager.get_scope_for_session("session-a")
    assert session1_again is session1


@pytest.mark.asyncio
async def test_full_chain_memory_scope_hierarchy(memory_manager):
    memory_manager.get_or_create("global", "default", ttl_seconds=86400)
    user_mem = memory_manager.get_or_create("user", "john", ttl_seconds=86400)
    session_mem = memory_manager.get_or_create(
        "session", "chat-1",
        parent_scope_type="user",
        parent_scope_id="john",
    )
    accessible = memory_manager.get_accessible_memories("session", "chat-1")
    assert len(accessible) >= 1


@pytest.mark.asyncio
async def test_full_chain_memory_cleanup(memory_manager):
    memory_manager.get_or_create("session", "expire-me", ttl_seconds=0.001)
    time.sleep(0.01)
    memory_manager._last_cleanup = 0
    memory_manager._cleanup_interval = 0
    memory_manager._maybe_cleanup()
    expired = memory_manager.get("session", "expire-me")
    assert expired is None


@pytest.mark.asyncio
async def test_full_chain_skill_from_rag_context(skill_engine, rag_engine, memory_manager):
    memory_skill = Skill(
        id="memory.alert.fix",
        name="High Memory Alert",
        triggers=[SkillTrigger(metric="memory.usage", operator=">", threshold=90)],
        tags=["memory", "linux"],
    )
    skill_engine.store.save(memory_skill)

    await rag_engine.index_fault_record(
        fault_id="mem-001",
        alert={"action": "memory.usage", "severity": "warning"},
        diagnosis="Memory usage at 95%, swap is full",
        resolution="Killed top memory consumer process (java)",
        tags=["memory", "oom"],
    )

    results = await rag_engine.query("high memory usage swap full", top_k=3)
    assert results.total_found > 0
    assert any("memory" in doc.content for doc in results.documents)
