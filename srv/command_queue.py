"""Command priority queue for managing multiple input sources."""
import asyncio
import time
from enum import IntEnum
from dataclasses import dataclass, field


class CommandPriority(IntEnum):
    """Lower value = higher priority."""
    API = 0
    OSC_PANEL = 1
    OSC_INTERACTION = 2
    GAME = 3


@dataclass(order=True)
class Command:
    priority: int
    timestamp: float = field(compare=True)
    channel: str = field(compare=False)
    action: str = field(compare=False)  # 'wave', 'strength', 'clear'
    value: object = field(compare=False, default=None)
    source_id: str = field(compare=False, default='')

    def __post_init__(self):
        if not self.timestamp:
            self.timestamp = time.time()


class CommandQueue:
    """Priority queue with per-source cooldown."""

    def __init__(self):
        self._queue: asyncio.PriorityQueue = asyncio.PriorityQueue()
        self._source_last_time: dict[str, float] = {}
        self._cooldowns: dict[CommandPriority, float] = {
            CommandPriority.API: 0,
            CommandPriority.OSC_PANEL: 0.1,
            CommandPriority.OSC_INTERACTION: 0.02,
            CommandPriority.GAME: 0.2,
        }
        self._enabled: dict[CommandPriority, bool] = {p: True for p in CommandPriority}

    def set_cooldown(self, priority: CommandPriority, seconds: float):
        self._cooldowns[priority] = seconds

    def set_enabled(self, priority: CommandPriority, enabled: bool):
        self._enabled[priority] = enabled

    async def put(self, priority: CommandPriority, channel: str, action: str,
                  value=None, source_id: str = '') -> bool:
        """Add command if not in cooldown. Returns True if accepted."""
        if not self._enabled.get(priority, True):
            return False

        now = time.time()
        key = f"{priority.name}_{source_id}"
        cooldown = self._cooldowns.get(priority, 0)
        if key in self._source_last_time:
            if now - self._source_last_time[key] < cooldown:
                return False

        self._source_last_time[key] = now
        cmd = Command(
            priority=priority.value,
            timestamp=now,
            channel=channel,
            action=action,
            value=value,
            source_id=source_id,
        )
        await self._queue.put(cmd)
        return True

    async def get(self) -> Command:
        """Get next command (blocks until available)."""
        return await self._queue.get()

    def task_done(self):
        self._queue.task_done()

    def empty(self) -> bool:
        return self._queue.empty()

    def clear(self):
        """Discard all pending commands and recreate queue for new event loop."""
        self._queue = asyncio.PriorityQueue()
        self._source_last_time.clear()
