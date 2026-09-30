"""
Agent Memory and State Management
Persistent storage for the co-founder agent's memory, context, and state.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional
from dataclasses import dataclass, asdict
from enum import Enum


class MemoryType(Enum):
    """Types of memories the agent can store."""
    CONVERSATION = "conversation"
    GOAL = "goal"
    TASK = "task"
    INSIGHT = "insight"
    DECISION = "decision"
    OPPORTUNITY = "opportunity"
    COMMITMENT = "commitment"


@dataclass
class Memory:
    """A single memory entry."""
    id: str
    type: MemoryType
    content: str
    metadata: Dict[str, Any]
    created_at: str
    updated_at: str
    tags: List[str]
    
    def to_dict(self) -> Dict:
        data = asdict(self)
        data['type'] = self.type.value
        return data
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Memory':
        data['type'] = MemoryType(data['type'])
        return cls(**data)


class AgentMemory:
    """
    Persistent memory system for the co-founder agent.
    Stores conversations, goals, insights, and context across sessions.
    """
    
    def __init__(self, memory_dir: str = "cofounder_agent/memory"):
        self.memory_dir = Path(memory_dir)
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        
        self.memories_file = self.memory_dir / "memories.json"
        self.context_file = self.memory_dir / "context.json"
        self.index_file = self.memory_dir / "index.json"
        
        self.memories: Dict[str, Memory] = {}
        self.context: Dict[str, Any] = {}
        self.index: Dict[str, List[str]] = {}
        
        self._load()
    
    def _load(self):
        """Load memories and context from disk."""
        if self.memories_file.exists():
            with open(self.memories_file, 'r') as f:
                data = json.load(f)
                self.memories = {
                    mem_id: Memory.from_dict(mem_data)
                    for mem_id, mem_data in data.items()
                }
        
        if self.context_file.exists():
            with open(self.context_file, 'r') as f:
                self.context = json.load(f)
        
        if self.index_file.exists():
            with open(self.index_file, 'r') as f:
                self.index = json.load(f)
    
    def _save(self):
        """Save memories and context to disk."""
        with open(self.memories_file, 'w') as f:
            data = {mem_id: mem.to_dict() for mem_id, mem in self.memories.items()}
            json.dump(data, f, indent=2)
        
        with open(self.context_file, 'w') as f:
            json.dump(self.context, f, indent=2)
        
        with open(self.index_file, 'w') as f:
            json.dump(self.index, f, indent=2)
    
    def add_memory(
        self,
        memory_type: MemoryType,
        content: str,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ) -> str:
        """Add a new memory and return its ID."""
        memory_id = f"{memory_type.value}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')}"
        now = datetime.now().isoformat()
        
        memory = Memory(
            id=memory_id,
            type=memory_type,
            content=content,
            metadata=metadata or {},
            created_at=now,
            updated_at=now,
            tags=tags or []
        )
        
        self.memories[memory_id] = memory
        
        # Update index
        type_key = memory_type.value
        if type_key not in self.index:
            self.index[type_key] = []
        self.index[type_key].append(memory_id)
        
        for tag in tags or []:
            tag_key = f"tag:{tag}"
            if tag_key not in self.index:
                self.index[tag_key] = []
            self.index[tag_key].append(memory_id)
        
        self._save()
        return memory_id
    
    def get_memory(self, memory_id: str) -> Optional[Memory]:
        """Retrieve a specific memory."""
        return self.memories.get(memory_id)
    
    def update_memory(
        self,
        memory_id: str,
        content: Optional[str] = None,
        metadata: Optional[Dict[str, Any]] = None,
        tags: Optional[List[str]] = None
    ):
        """Update an existing memory."""
        if memory_id not in self.memories:
            raise ValueError(f"Memory {memory_id} not found")
        
        memory = self.memories[memory_id]
        
        if content is not None:
            memory.content = content
        if metadata is not None:
            memory.metadata.update(metadata)
        if tags is not None:
            memory.tags = tags
        
        memory.updated_at = datetime.now().isoformat()
        
        self._save()
    
    def query_memories(
        self,
        memory_type: Optional[MemoryType] = None,
        tags: Optional[List[str]] = None,
        limit: Optional[int] = None
    ) -> List[Memory]:
        """Query memories by type and/or tags."""
        memory_ids = set()
        
        if memory_type:
            memory_ids = set(self.index.get(memory_type.value, []))
        else:
            memory_ids = set(self.memories.keys())
        
        if tags:
            for tag in tags:
                tag_key = f"tag:{tag}"
                tag_ids = set(self.index.get(tag_key, []))
                memory_ids &= tag_ids
        
        results = [self.memories[mem_id] for mem_id in memory_ids if mem_id in self.memories]
        results.sort(key=lambda m: m.created_at, reverse=True)
        
        if limit:
            results = results[:limit]
        
        return results
    
    def get_context(self, key: str, default: Any = None) -> Any:
        """Get a context value."""
        return self.context.get(key, default)
    
    def set_context(self, key: str, value: Any):
        """Set a context value."""
        self.context[key] = value
        self._save()
    
    def update_context(self, updates: Dict[str, Any]):
        """Update multiple context values."""
        self.context.update(updates)
        self._save()
    
    def get_recent_activity(self, days: int = 7) -> List[Memory]:
        """Get recent memories from the last N days."""
        from datetime import timedelta
        cutoff = datetime.now() - timedelta(days=days)
        cutoff_str = cutoff.isoformat()
        
        recent = [
            mem for mem in self.memories.values()
            if mem.created_at >= cutoff_str
        ]
        recent.sort(key=lambda m: m.created_at, reverse=True)
        return recent
    
    def get_summary(self) -> Dict[str, Any]:
        """Get a summary of the agent's memory."""
        return {
            "total_memories": len(self.memories),
            "by_type": {
                mem_type.value: len(self.index.get(mem_type.value, []))
                for mem_type in MemoryType
            },
            "context_keys": list(self.context.keys()),
            "recent_activity_count": len(self.get_recent_activity(days=7))
        }
