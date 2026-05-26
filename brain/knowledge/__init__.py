"""SKILL Engine — fault → fix → rollback knowledge base for AI Ops.

Each SKILL is a versioned, validated recovery procedure for a known type
of incident. The engine supports:

- Semantic matching: given an alert or diagnosis, find the most relevant SKILL
- Versioned rollback: every SKILL has a verified rollback plan
- Success rate tracking: auto-tracking of how often a SKILL succeeds
- Auto-learning: Reflector can create new SKILLs from novel incidents

SKILL Storage format (YAML):
`yaml
skill_id: disk.cleanup.v2
name: Disk Space Cleanup
version: 2
triggers:
  - metric: disk.usage
    op: ">"
    threshold: 85
    unit: "%"
diagnosis_steps:
  - "Check /var/log size"
  - "Check Docker overlay layer"
  - "Check core dump files"
remediation:
  actions:
    - tool: exec.run
      params: {command: "journalctl --vacuum-size=500M"}
  rollback_plan:
    - tool: exec.run
      params: {command: "systemctl restart rsyslog"}
  verification:
    tool: disk.usage
    params: {path: "/"}
tags: [linux, disk, high-frequency]
success_rate: 0.96
last_verified: "2026-05-20"
`
"""

import hashlib
import json
import os
import time
import yaml
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Any, Optional
from datetime import datetime


# --- Data Models ---


@dataclass
class SkillAction:
    tool: str
    params: dict[str, Any] = field(default_factory=dict)
    rollback: str = ""
    timeout_seconds: int = 60


@dataclass
class SkillTrigger:
    metric: str
    operator: str  # >, <, ==, !=, contains
    threshold: Any
    unit: str = ""


@dataclass
class SkillVerification:
    tool: str = ""
    params: dict[str, Any] = field(default_factory=dict)
    expected: dict[str, Any] = field(default_factory=dict)


@dataclass
class Skill:
    id: str
    name: str
    version: int = 1
    description: str = ""
    triggers: list[SkillTrigger] = field(default_factory=list)
    diagnosis_steps: list[str] = field(default_factory=list)
    remediation_actions: list[SkillAction] = field(default_factory=list)
    rollback_plan: list[SkillAction] = field(default_factory=list)
    verification: SkillVerification = field(default_factory=SkillVerification)
    tags: list[str] = field(default_factory=list)
    success_rate: float = 0.0
    total_attempts: int = 0
    total_successes: int = 0
    last_verified: str = ""
    created_at: str = ""
    updated_at: str = ""
    source: str = "builtin"  # builtin | auto_learned | manual

    def matches_alert(self, alert: dict[str, Any]) -> float:
        """Score how well this SKILL matches an alert/fault."""
        score = 0.0
        alert_str = json.dumps(alert).lower()

        for trigger in self.triggers:
            metric_value = self._resolve_metric(alert, trigger.metric)
            if metric_value is not None:
                if self._compare(metric_value, trigger.threshold, trigger.operator):
                    score += 0.5

        # Tag matching
        alert_tags = alert.get("tags", [])
        if alert_tags:
            matched_tags = set(self.tags) & set(alert_tags)
            score += len(matched_tags) * 0.2

        # Keyword matching in alert message
        message = alert.get("message", "").lower()
        name_keywords = self.name.lower().split()
        if any(kw in message for kw in name_keywords):
            score += 0.3

        # Success rate bonus
        if self.total_attempts > 5 and self.success_rate > 0.8:
            score += 0.2

        return min(score, 1.0)

    def record_result(self, success: bool) -> None:
        """Record the outcome of a SKILL execution."""
        self.total_attempts += 1
        if success:
            self.total_successes += 1
        self.success_rate = self.total_successes / max(self.total_attempts, 1)

    @staticmethod
    def _resolve_metric(data: dict, path: str) -> Any:
        parts = path.split(".")
        current = data
        for part in parts:
            if isinstance(current, dict):
                current = current.get(part)
            else:
                return None
        return current

    @staticmethod
    def _compare(actual: Any, threshold: Any, operator: str) -> bool:
        try:
            actual_num = float(actual)
            threshold_num = float(threshold)
            if operator == ">":
                return actual_num > threshold_num
            elif operator == "<":
                return actual_num < threshold_num
            elif operator == ">=":
                return actual_num >= threshold_num
            elif operator == "<=":
                return actual_num <= threshold_num
            elif operator == "==":
                return actual_num == threshold_num
        except (ValueError, TypeError):
            pass
        str_actual = str(actual)
        str_threshold = str(threshold)
        if operator == "==":
            return str_actual == str_threshold
        elif operator == "contains":
            return str_threshold in str_actual
        return False


# --- Skill Store ---


class SkillStore:
    """Persistent SKILL storage using YAML files on disk."""

    def __init__(self, skills_dir: str = None):
        if skills_dir is None:
            skills_dir = os.environ.get(
                "SKILLS_DIR",
                str(Path.home() / ".gaiops" / "skills")
            )
        self.skills_dir = Path(skills_dir)
        self.skills_dir.mkdir(parents=True, exist_ok=True)
        self._skills: dict[str, Skill] = {}
        self._load_all()

    def _load_all(self) -> None:
        """Load all SKILL YAML files from disk."""
        for f in self.skills_dir.glob("*.yaml"):
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    data = yaml.safe_load(fh)
                if data and "skill_id" in data:
                    skill = self._dict_to_skill(data)
                    self._skills[skill.id] = skill
            except Exception as e:
                pass  # Skip malformed skills

    def _skill_path(self, skill_id: str) -> Path:
        return self.skills_dir / f"{skill_id}.yaml"

    def _dict_to_skill(self, data: dict) -> Skill:
        triggers = []
        for t in data.get("triggers", []):
            triggers.append(SkillTrigger(
                metric=t.get("metric", ""),
                operator=t.get("op", "=="),
                threshold=t.get("threshold"),
                unit=t.get("unit", ""),
            ))

        actions = []
        for a in data.get("remediation", {}).get("actions", []):
            actions.append(SkillAction(
                tool=a.get("tool", ""),
                params=a.get("params", {}),
                rollback=a.get("rollback", ""),
                timeout_seconds=a.get("timeout_seconds", 60),
            ))

        rollback = []
        for a in data.get("remediation", {}).get("rollback_plan", []):
            rollback.append(SkillAction(
                tool=a.get("tool", ""),
                params=a.get("params", {}),
                timeout_seconds=a.get("timeout_seconds", 60),
            ))

        ver = data.get("remediation", {}).get("verification", {})
        verification = SkillVerification(
            tool=ver.get("tool", ""),
            params=ver.get("params", {}),
            expected=ver.get("expected", {}),
        )

        now = datetime.utcnow().isoformat()
        return Skill(
            id=data["skill_id"],
            name=data.get("name", ""),
            version=data.get("version", 1),
            description=data.get("description", ""),
            triggers=triggers,
            diagnosis_steps=data.get("diagnosis_steps", []),
            remediation_actions=actions,
            rollback_plan=rollback,
            verification=verification,
            tags=data.get("tags", []),
            success_rate=data.get("success_rate", 0.0),
            total_attempts=data.get("total_attempts", 0),
            total_successes=data.get("total_successes", 0),
            last_verified=data.get("last_verified", ""),
            created_at=data.get("created_at", now),
            updated_at=data.get("updated_at", now),
            source=data.get("source", "builtin"),
        )

    def get(self, skill_id: str) -> Optional[Skill]:
        return self._skills.get(skill_id)

    def list_all(self) -> list[Skill]:
        return list(self._skills.values())

    def save(self, skill: Skill) -> None:
        """Save a SKILL to disk."""
        data = {
            "skill_id": skill.id,
            "name": skill.name,
            "version": skill.version,
            "description": skill.description,
            "triggers": [
                {"metric": t.metric, "op": t.operator,
                 "threshold": t.threshold, "unit": t.unit}
                for t in skill.triggers
            ],
            "diagnosis_steps": skill.diagnosis_steps,
            "remediation": {
                "actions": [
                    {"tool": a.tool, "params": a.params,
                     "rollback": a.rollback, "timeout_seconds": a.timeout_seconds}
                    for a in skill.remediation_actions
                ],
                "rollback_plan": [
                    {"tool": a.tool, "params": a.params,
                     "timeout_seconds": a.timeout_seconds}
                    for a in skill.rollback_plan
                ],
                "verification": {
                    "tool": skill.verification.tool,
                    "params": skill.verification.params,
                    "expected": skill.verification.expected,
                },
            },
            "tags": skill.tags,
            "success_rate": skill.success_rate,
            "total_attempts": skill.total_attempts,
            "total_successes": skill.total_successes,
            "last_verified": skill.last_verified,
            "created_at": skill.created_at,
            "updated_at": datetime.utcnow().isoformat(),
            "source": skill.source,
        }
        path = self._skill_path(skill.id)
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, allow_unicode=True)
        self._skills[skill.id] = skill

    def delete(self, skill_id: str) -> bool:
        path = self._skill_path(skill_id)
        if path.exists():
            path.unlink()
        return self._skills.pop(skill_id, None) is not None


# --- Skill Engine ---


class SkillEngine:
    """Matches alerts to SKILLs and manages execution lifecycle."""

    def __init__(self, store: SkillStore):
        self.store = store
        self._execution_history: dict[str, list[bool]] = {}

    def find_best_skill(self, alert: dict[str, Any]) -> Optional[Skill]:
        """Find the best matching SKILL for an alert."""
        best_skill = None
        best_score = 0.3  # Minimum threshold

        for skill in self.store.list_all():
            score = skill.matches_alert(alert)
            if score > best_score:
                best_score = score
                best_skill = skill

        return best_skill

    def find_skills_by_tag(self, tag: str) -> list[Skill]:
        return [s for s in self.store.list_all() if tag in s.tags]

    def record_execution(self, skill_id: str, success: bool) -> None:
        skill = self.store.get(skill_id)
        if skill:
            skill.record_result(success)
            self.store.save(skill)

    def get_statistics(self) -> dict[str, Any]:
        skills = self.store.list_all()
        total = len(skills)
        if total == 0:
            return {"total": 0}
        avg_success = sum(s.success_rate for s in skills) / total
        return {
            "total": total,
            "avg_success_rate": round(avg_success, 2),
            "auto_learned": sum(1 for s in skills if s.source == "auto_learned"),
            "builtin": sum(1 for s in skills if s.source == "builtin"),
            "high_confidence": sum(1 for s in skills if s.success_rate > 0.8),
        }
