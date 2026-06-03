from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from smhelper.platforms.xhs.browser.live_room_operator import (
    XhsLiveRoomBrowserOperator,
)


@dataclass
class FakeLiveRoomSession:
    sent_comments: list[str] = field(default_factory=list)
    closed: bool = False
    health_checks: int = 0

    def send_comment(self, text: str) -> None:
        self.sent_comments.append(text)

    def check_health(self) -> None:
        self.health_checks += 1

    def close(self) -> None:
        self.closed = True


@dataclass
class FailingLiveRoomSession:
    def send_comment(self, text: str) -> None:
        raise RuntimeError(f"cannot send {text}")

    def check_health(self) -> None:
        raise RuntimeError("page closed")

    def close(self) -> None:
        raise RuntimeError("cannot close")


@dataclass
class FakeSessionManager:
    session: FakeLiveRoomSession | FailingLiveRoomSession
    opened: list[tuple[str, str, Path]] = field(default_factory=list)

    def open_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> FakeLiveRoomSession | FailingLiveRoomSession:
        self.opened.append((session_id, room_url, storage_state_path))
        return self.session


@dataclass
class FailingSessionManager:
    def open_live_room(
        self,
        *,
        session_id: str,
        room_url: str,
        storage_state_path: Path,
    ) -> FakeLiveRoomSession:
        raise RuntimeError(f"cannot open {session_id}")


def test_xhs_operator_enters_room_and_keeps_session_for_send_and_close(
    tmp_path: Path,
) -> None:
    live_session = FakeLiveRoomSession()
    manager = FakeSessionManager(session=live_session)
    operator = XhsLiveRoomBrowserOperator(session_manager=manager)

    enter_result = operator.enter_live_room(
        session_id="session-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        storage_state_path=tmp_path / "storage_state.json",
    )
    send_result = operator.send_comment(
        session_id="session-1",
        final_text="Is this suitable for oily skin?",
    )
    check_result = operator.check_session(session_id="session-1")
    close_result = operator.close_session(session_id="session-1")

    assert enter_result.success is True
    assert send_result.success is True
    assert check_result.success is True
    assert close_result.success is True
    assert manager.opened == [
        (
            "session-1",
            "https://www.xiaohongshu.com/livestream/1",
            tmp_path / "storage_state.json",
        )
    ]
    assert live_session.sent_comments == ["Is this suitable for oily skin?"]
    assert live_session.health_checks == 1
    assert live_session.closed is True


def test_xhs_operator_reports_send_failure_when_session_is_not_open() -> None:
    operator = XhsLiveRoomBrowserOperator(
        session_manager=FakeSessionManager(session=FakeLiveRoomSession())
    )

    result = operator.send_comment(
        session_id="missing-session",
        final_text="hello",
    )

    assert result.success is False
    assert result.failure_reason == "live room session is not open: missing-session"


def test_xhs_operator_reports_close_failure_when_session_is_not_open() -> None:
    operator = XhsLiveRoomBrowserOperator(
        session_manager=FakeSessionManager(session=FakeLiveRoomSession())
    )

    result = operator.close_session(session_id="missing-session")

    assert result.success is False
    assert result.failure_reason == "live room session is not open: missing-session"


def test_xhs_operator_reports_check_failure_when_session_is_not_open() -> None:
    operator = XhsLiveRoomBrowserOperator(
        session_manager=FakeSessionManager(session=FakeLiveRoomSession())
    )

    result = operator.check_session(session_id="missing-session")

    assert result.success is False
    assert result.failure_reason == "live room session is not open: missing-session"


def test_xhs_operator_maps_browser_exceptions_to_action_failures(
    tmp_path: Path,
) -> None:
    enter_failed = XhsLiveRoomBrowserOperator(
        session_manager=FailingSessionManager()
    ).enter_live_room(
        session_id="session-1",
        room_url="https://www.xiaohongshu.com/livestream/1",
        storage_state_path=tmp_path / "storage_state.json",
    )
    failing_session = FailingLiveRoomSession()
    operator = XhsLiveRoomBrowserOperator(
        session_manager=FakeSessionManager(session=failing_session)
    )
    operator.enter_live_room(
        session_id="session-2",
        room_url="https://www.xiaohongshu.com/livestream/2",
        storage_state_path=tmp_path / "storage_state.json",
    )

    send_failed = operator.send_comment(session_id="session-2", final_text="hello")
    check_failed = operator.check_session(session_id="session-2")
    close_failed = operator.close_session(session_id="session-2")

    assert enter_failed.success is False
    assert enter_failed.failure_reason == "cannot open session-1"
    assert send_failed.success is False
    assert send_failed.failure_reason == "cannot send hello"
    assert check_failed.success is False
    assert check_failed.failure_reason == "page closed"
    assert close_failed.success is False
    assert close_failed.failure_reason == "cannot close"
