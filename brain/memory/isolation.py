"""Memory Isolation System — prevents cross-contamination between sessions,
users, and managed nodes.

Isolation levels:
  1. Session-level: each conversation/incident has its own context
  2. User-level: different operators get separate memory spaces
  3. Node-level: each managed node has independent fault history
  4. Tenant-level (future): multi-tenant isolation

Design pattern:
  MemoryIsolationManager acts as a factory and access controller.
  Each scope gets its own WorkingMemory, EpisodicMemory, and SemanticMemory
  instances. Scopes inherit from parent scopes (read-only).
"""

import copy
import time
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class MemoryScope:
    """Identifies a unique memory isolation scope."""
    scope_type: str  # "session" | "user" | "node" | "global"
    scope_id: str
    parent_scope_type: Optional[str] = None
    parent_scope_id: Optional[str] = None

    def key(self) -> str:
        return f"{self.scope_type}:{self.scope_id}"

    def parent_key(self) -> Optional[str]:
        if self.parent_scope_type and self.parent_scope_id:
            return f"{self.parent_scope_type}:{self.parent_scope_id}"
        return None


@dataclass
class IsolatedMemory:
    """The memory bundle for a single scope.
    
    Contains pointers to memory modules, not the modules themselves,
    to avoid circular imports. The actual memory objects are stored
    in the manager's registry.
    """
    scope: MemoryScope
    working_memory: Any = None  # WorkingMemory instance
    episodic_memory: Any = None  # EpisodicMemory instance
    semantic_memory: Any = None  # SemanticMemory instance
    created_at: float = 0.0
    last_accessed: float = 0.0
    access_count: int = 0
    ttl_seconds: float = 3600.0  # Auto-expire after 1 hour of inactivity
    read_only: bool = False  # Inherited scopes are read-only


class MemoryIsolationManager:
    """Manages isolated memory spaces with automatic cleanup.
    
    Scopes form a hierarchy:
      global → user:{user_id} → session:{session_id}
      global → node:{node_id} → session:{session_id}
    
    Session scopes inherit from both user and node scopes.
    """

    def __init__(self, cleanup_interval: float = 300.0):
        self._memories: dict[str, IsolatedMemory] = {}
        self._last_cleanup: float = time.time()
        self._cleanup_interval = cleanup_interval

    def get_or_create(
        self,
        scope_type: str,
        scope_id: str,
        parent_scope_type: Optional[str] = None,
        parent_scope_id: Optional[str] = None,
        ttl_seconds: float = 3600.0,
    ) -> IsolatedMemory:
        """Get existing memory for scope or create new one."""
        scope = MemoryScope(
            scope_type=scope_type,
            scope_id=scope_id,
            parent_scope_type=parent_scope_type,
            parent_scope_id=parent_scope_id,
        )
        key = scope.key()

        if key in self._memories:
            memory = self._memories[key]
            memory.last_accessed = time.time()
            memory.access_count += 1
            return memory

        # Create new isolated memory
        memory = IsolatedMemory(
            scope=scope,
            created_at=time.time(),
            last_accessed=time.time(),
            access_count=1,
            ttl_seconds=ttl_seconds,
        )
        self._memories[key] = memory
        self._maybe_cleanup()
        return memory

    def get(self, scope_type: str, scope_id: str) -> Optional[IsolatedMemory]:
        """Get existing memory without creating."""
        key = MemoryScope(scope_type=scope_type, scope_id=scope_id).key()
        memory = self._memories.get(key)
        if memory:
            memory.last_accessed = time.time()
            memory.access_count += 1
        return memory

    def delete_scope(self, scope_type: str, scope_id: str) -> bool:
        """Explicitly delete a memory scope (session end, user logout)."""
        key = MemoryScope(scope_type=scope_type, scope_id=scope_id).key()
        if key in self._memories:
            del self._memories[key]
            return True
        return False

    def get_scope_for_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
        node_id: Optional[str] = None,
    ) -> tuple[IsolatedMemory, list[IsolatedMemory]]:
        """Get session memory with inherited context from user and node.
        
        Returns:
            (session_memory, [inherited_memories])
        """
        # Ensure parent scopes exist
        if user_id:
            self.get_or_create("user", user_id, ttl_seconds=86400.0)
        if node_id:
            self.get_or_create("node", node_id, ttl_seconds=86400.0)

        # Determine parent (user takes priority over node for inheritance)
        parent_type = user_id and "user" or node_id and "node" or None
        parent_id = user_id or node_id or None

        session_memory = self.get_or_create(
            "session", session_id,
            parent_scope_type=parent_type,
            parent_scope_id=parent_id,
            ttl_seconds=3600.0,
        )

        # Collect inherited memories
        inherited = []
        if user_id:
            user_mem = self.get("user", user_id)
            if user_mem:
                inherited.append(user_mem)
        if node_id:
            node_mem = self.get("node", node_id)
            if node_mem:
                inherited.append(node_mem)

        return session_memory, inherited

    def get_accessible_memories(
        self,
        scope_type: str,
        scope_id: str,
    ) -> list[IsolatedMemory]:
        """Get all memories accessible from a scope (including inherited)."""
        result = []
        scope = MemoryScope(scope_type=scope_type, scope_id=scope_id)
        key = scope.key()

        memory = self._memories.get(key)
        if memory:
            result.append(memory)

        # Follow parent chain using stored scope's parent info
        current = memory.scope
        visited = {key}
        while current.parent_scope_type and current.parent_scope_id:
            parent_key = current.parent_key()
            if parent_key in visited:
                break
            visited.add(parent_key)
            parent_memory = self._memories.get(parent_key)
            if parent_memory:
                result.append(parent_memory)
                current = parent_memory.scope
            else:
                break

        return result

    def _maybe_cleanup(self) -> None:
        """Periodic cleanup of expired memories."""
        now = time.time()
        if now - self._last_cleanup < self._cleanup_interval:
            return
        self._last_cleanup = now

        expired_keys = []
        for key, memory in self._memories.items():
            if memory.scope.scope_type == "session":
                # Session memories expire quickly
                if now - memory.last_accessed > memory.ttl_seconds:
                    expired_keys.append(key)
            elif memory.scope.scope_type in ("user", "node"):
                # User/node memories last longer
                if now - memory.last_accessed > memory.ttl_seconds * 24:
                    expired_keys.append(key)

        for key in expired_keys:
            del self._memories[key]

    def cleanup_all_sessions(self) -> int:
        """Clean all session-level memories (used during system reset)."""
        count = 0
        for key in list(self._memories.keys()):
            if key.startswith("session:"):
                del self._memories[key]
                count += 1
        return count

    def stats(self) -> dict[str, Any]:
        now = time.time()
        session_count = sum(1 for k in self._memories if k.startswith("session:"))
        user_count = sum(1 for k in self._memories if k.startswith("user:"))
        node_count = sum(1 for k in self._memories if k.startswith("node:"))
        global_count = sum(1 for k in self._memories if k.startswith("global:"))
        return {
            "total_scopes": len(self._memories),
            "sessions": session_count,
            "users": user_count,
            "nodes": node_count,
            "global": global_count,
        }
