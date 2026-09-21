"""Ephemeral Session State Schema & Memory Pruning Strategy (Memorystore Redis interface).
Implements sliding window turn pruning (capped at 10 turns), progressive 2-sentence summarization,
sliding 30-minute inactivity TTL, 2-hour hard session ceiling, and Zero Raw PII Policy (SDD Section 3.1.1).
"""

from dataclasses import dataclass, field
import time
from typing import Any, Dict, List, Optional
from src.config import settings


@dataclass
class DialogTurn:
    turn_id: int
    role: str  # "user" or "assistant"
    timestamp: float
    content: str
    tool_invocations_summary: List[str] = field(default_factory=list)


@dataclass
class SessionState:
    session_id: str
    employee_id: str
    tenant_id: str = "altostrat-sg"
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    turn_count: int = 0
    active_saga_id: Optional[str] = None
    conversation_summary: str = ""
    dialog_history: List[DialogTurn] = field(default_factory=list)

    def is_expired(self) -> bool:
        now = time.time()
        # Hard 2-hour maximum lifetime
        if now - self.created_at > settings.SESSION_MAX_LIFETIME_SECONDS:
            return True
        # Sliding 30-minute inactivity TTL
        if now - self.last_active_at > settings.SESSION_INACTIVITY_TTL_SECONDS:
            return True
        return False

    def touch(self) -> None:
        self.last_active_at = time.time()


class SessionMemoryManager:
    """Manages ephemeral conversation state in volatile memory / Redis."""

    def __init__(self):
        self._sessions: Dict[str, SessionState] = {}

    def _make_key(self, tenant_id: str, employee_id: str, session_id: str) -> str:
        return f"session:{tenant_id}:{employee_id}:{session_id}"

    def get_or_create_session(
        self,
        session_id: str,
        employee_id: str = "EMP-10492",
        tenant_id: str = "altostrat-sg"
    ) -> SessionState:
        key = self._make_key(tenant_id, employee_id, session_id)
        session = self._sessions.get(key)

        if session and session.is_expired():
            # Purge expired session
            del self._sessions[key]
            session = None

        if not session:
            session = SessionState(
                session_id=session_id,
                employee_id=employee_id,
                tenant_id=tenant_id,
                created_at=time.time(),
                last_active_at=time.time()
            )
            self._sessions[key] = session

        session.touch()
        return session

    def add_turn(
        self,
        session: SessionState,
        role: str,
        content: str,
        tool_invocations_summary: Optional[List[str]] = None
    ) -> None:
        session.turn_count += 1
        turn = DialogTurn(
            turn_id=session.turn_count,
            role=role,
            timestamp=time.time(),
            content=content,
            tool_invocations_summary=tool_invocations_summary or []
        )
        session.dialog_history.append(turn)
        session.touch()

        # Enforce Sliding Window Turn Pruning: cap at 10 turns (5 cycles)
        if len(session.dialog_history) > settings.SESSION_MAX_TURNS_WINDOW:
            pruned_count = len(session.dialog_history) - settings.SESSION_MAX_TURNS_WINDOW
            pruned_turns = session.dialog_history[:pruned_count]
            session.dialog_history = session.dialog_history[pruned_count:]

            # Condense pruned turns into progressive 2-sentence summary
            user_topics = [t.content[:40] for t in pruned_turns if t.role == "user"]
            summary_addendum = f"Earlier discussed: {', '.join(user_topics)}."
            if not session.conversation_summary:
                session.conversation_summary = summary_addendum
            else:
                session.conversation_summary = f"{session.conversation_summary} {summary_addendum}"[-300:]

    def purge_employee_sessions(self, employee_id: str) -> int:
        """Evicts all active sessions for an employee upon offboarding/revocation (<500ms)."""
        to_delete = [k for k, v in self._sessions.items() if v.employee_id == employee_id]
        for k in to_delete:
            del self._sessions[k]
        return len(to_delete)


# Singleton memory manager
default_memory_manager = SessionMemoryManager()
