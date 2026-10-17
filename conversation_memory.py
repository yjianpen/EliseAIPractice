"""Per-user conversational memory bounded by a sliding time window (default: the last 2 hours).

Each user_id has its own history, so one resident never sees another's messages. Turns older than the
window are dropped whenever that user's memory is touched, and users with no recent turns are removed
entirely, so memory stays bounded. In-process only: it resets when the process restarts.
"""
from __future__ import annotations

import threading
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Callable


@dataclass(frozen=True)
class Turn:
    role: str          # "user" or "assistant"
    text: str
    at: datetime


@dataclass
class ConversationMemory:
    window: timedelta = timedelta(hours=2)
    max_turns_per_user: int = 200        # hard cap per user, in case of a message flood
    clock: Callable[[], datetime] = datetime.now
    _turns: dict[str, deque[Turn]] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def add(self, user_id: str, role: str, text: str) -> None:
        """Record one turn for this user, timestamped now."""
        with self._lock:
            turns = self._turns.setdefault(user_id, deque(maxlen=self.max_turns_per_user))
            turns.append(Turn(role, text, self.clock()))
            self._prune(user_id)

    def recent(self, user_id: str) -> list[Turn]:
        """This user's turns from the last `window`, oldest first. Unknown users get []."""
        with self._lock:
            self._prune(user_id)
            return list(self._turns.get(user_id, ()))

    def _prune(self, user_id: str) -> None:
        """Drop turns older than the window (they are in time order); forget the user if none remain."""
        turns = self._turns.get(user_id)
        if turns is None:
            return
        cutoff = self.clock() - self.window
        while turns and turns[0].at < cutoff:
            turns.popleft()
        if not turns:
            del self._turns[user_id]
