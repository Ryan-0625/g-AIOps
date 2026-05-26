"""Tests for the SKILL engine (knowledge/__init__.py)."""

import os
import tempfile
import pytest
from knowledge import SkillEngine, SkillStore, Skill, SkillTrigger, SkillAction, SkillVerification


@pytest.fixture
def skills_dir():
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def store(skills_dir):
    return SkillStore(skills_dir)


@pytest.fixture
def engine(store):
    return SkillEngine(store)


def test_skill_store_create_and_retrieve(store):
    skill = Skill(
        id="test.skill.v1",
        name="Test Skill",
        triggers=[SkillTrigger(metric="cpu.usage", operator=">", threshold=90)],
        remediation_actions=[SkillAction(tool="exec.run", params={"command": "echo test"})],
        tags=["linux", "test"],
    )
    store.save(skill)
    retrieved = store.get("test.skill.v1")
    assert retrieved is not None
    assert retrieved.name == "Test Skill"
    assert len(retrieved.triggers) == 1
    assert retrieved.triggers[0].metric == "cpu.usage"


def test_skill_store_list(store):
    store.save(Skill(id="a", name="A"))
    store.save(Skill(id="b", name="B"))
    skills = store.list_all()
    assert len(skills) == 2


def test_skill_store_delete(store):
    store.save(Skill(id="del.me", name="Delete Me"))
    assert store.delete("del.me") is True
    assert store.get("del.me") is None
    assert store.delete("nonexistent") is False


def test_skill_matches_alert_by_metric(store):
    skill = Skill(
        id="disk.cleanup",
        name="Disk Cleanup",
        triggers=[SkillTrigger(metric="disk.usage", operator=">", threshold=85)],
        tags=["disk"],
    )
    store.save(skill)

    # Should match high disk usage
    score = skill.matches_alert({"disk": {"usage": 90}, "tags": ["disk"]})
    assert score > 0.5

    # Should not match low disk usage
    low_score = skill.matches_alert({"disk": {"usage": 30}})
    assert low_score < 0.5


def test_skill_matches_alert_by_tags(store):
    skill = Skill(
        id="nginx.restart",
        name="Nginx Restart",
        triggers=[],
        tags=["nginx", "web"],
    )
    score = skill.matches_alert({"tags": ["nginx"], "message": "connection refused"})
    assert score > 0


def test_skill_records_result(store):
    skill = Skill(id="test.record", name="Test Record")
    store.save(skill)

    skill.record_result(True)
    skill.record_result(True)
    skill.record_result(False)

    assert skill.total_attempts == 3
    assert skill.total_successes == 2
    assert skill.success_rate == 2.0 / 3.0


def test_skill_engine_find_best(engine):
    engine.store.save(Skill(
        id="disk.cleanup",
        name="Disk Cleanup",
        triggers=[SkillTrigger(metric="disk.usage", operator=">", threshold=85)],
        tags=["disk"],
    ))
    engine.store.save(Skill(
        id="cpu.alerts",
        name="CPU Alert",
        triggers=[SkillTrigger(metric="cpu.usage", operator=">", threshold=90)],
        tags=["cpu"],
    ))

    best = engine.find_best_skill({"disk": {"usage": 95}, "tags": ["disk"]})
    assert best is not None
    assert best.id == "disk.cleanup"

    # No matching skill
    unknown = engine.find_best_skill({"memory": {"usage": 99}})
    assert unknown is None


def test_skill_engine_statistics(engine):
    skill = Skill(id="test.stats", name="Test Stats")
    skill.record_result(True)
    skill.record_result(True)
    engine.store.save(skill)

    stats = engine.get_statistics()
    assert stats["total"] == 1
    assert stats["avg_success_rate"] > 0


def test_skill_engine_find_by_tag(engine):
    engine.store.save(Skill(id="a", name="A", tags=["linux"]))
    engine.store.save(Skill(id="b", name="B", tags=["linux", "disk"]))
    engine.store.save(Skill(id="c", name="C", tags=["windows"]))

    linux_skills = engine.find_skills_by_tag("linux")
    assert len(linux_skills) == 2

    disk_skills = engine.find_skills_by_tag("disk")
    assert len(disk_skills) == 1


def test_skill_trigger_compare_numeric():
    t = SkillTrigger(metric="x", operator=">", threshold=50)
    assert Skill._compare(75, 50, ">")
    assert not Skill._compare(25, 50, ">")


def test_skill_trigger_compare_contains():
    assert Skill._compare("error in log", "error", "contains")
    assert not Skill._compare("all good", "error", "contains")


def test_skill_trigger_compare_equals():
    assert Skill._compare("active", "active", "==")
    assert not Skill._compare("inactive", "active", "==")


def test_skill_trigger_resolve_nested():
    data = {"a": {"b": {"c": 42}}}
    assert Skill._resolve_metric(data, "a.b.c") == 42
    assert Skill._resolve_metric(data, "a.b") == {"c": 42}
    assert Skill._resolve_metric(data, "x.y.z") is None
