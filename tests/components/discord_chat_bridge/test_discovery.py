from __future__ import annotations

from dataclasses import dataclass

from custom_components.discord_chat_bridge.discovery import async_schedule_discovery_refresh


@dataclass
class FakeTask:
    done_value: bool = False
    cancelled: bool = False

    def done(self) -> bool:
        return self.done_value

    def cancel(self) -> None:
        self.cancelled = True


@dataclass
class FakeRuntime:
    entry_id: str
    discovery_refresh_task: FakeTask | None = None


class FakeHass:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def async_create_background_task(self, target, name: str, eager_start: bool = True):
        target.close()
        self.calls.append(name)
        return FakeTask()


async def test_async_schedule_discovery_refresh_skips_when_task_already_running() -> None:
    hass = FakeHass()
    runtime = FakeRuntime(entry_id="entry-1", discovery_refresh_task=FakeTask())

    await async_schedule_discovery_refresh(hass, object(), runtime)

    assert hass.calls == []


async def test_async_schedule_discovery_refresh_creates_task_when_idle() -> None:
    hass = FakeHass()
    runtime = FakeRuntime(entry_id="entry-1")

    await async_schedule_discovery_refresh(hass, object(), runtime)

    assert hass.calls == ["entry-1_discovery_refresh"]
    assert runtime.discovery_refresh_task is not None
