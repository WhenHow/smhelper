"""Application handlers for account scheduling and comment dispatch."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from smhelper.core.clock import Clock
from smhelper.core.ids import IdGenerator
from smhelper.live_assistant.application.commands import (
    EnterLiveRoomCommand,
    LoginXhsAccountCommand,
    SendCommentCommand,
)
from smhelper.live_assistant.application.exceptions import EntityNotFound
from smhelper.live_assistant.application.ports import (
    AccountLoginBrowserPort,
    LiveRoomAutomationPort,
    UnitOfWork,
    VerificationCodeProvider,
)
from smhelper.live_assistant.domain.models import (
    Account,
    AccountAuthProfile,
    CommentDispatch,
    CommentDispatchStatus,
    CommentMessage,
    LiveRoom,
    LiveRoomSession,
    SessionStatus,
)
from smhelper.live_assistant.domain.services import (
    AccountSchedulingService,
    CommentDispatchPolicy,
)


@dataclass(frozen=True, slots=True)
class LoginXhsAccountResult:
    """Application result for an interactive XHS login."""

    account_id: str
    platform: str
    profile_dir: Path
    status: str
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class EnterLiveRoomResult:
    """Application result for an enter-room attempt."""

    session_id: str
    status: SessionStatus
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class SendCommentResult:
    """Application result for a send-comment attempt."""

    dispatch_id: str
    status: CommentDispatchStatus
    failure_reason: str | None = None


@dataclass(frozen=True, slots=True)
class LoginXhsAccountHandler:
    """Open CloakBrowser for manual XHS login and save profile metadata."""

    uow: UnitOfWork
    browser: AccountLoginBrowserPort
    clock: Clock
    profiles_root: Path
    verification_code_provider: VerificationCodeProvider | None = None
    platform: str = "xhs"

    def handle(self, command: LoginXhsAccountCommand) -> LoginXhsAccountResult:
        """Open the login browser and persist the reusable auth profile."""
        profile_dir = self.profiles_root / self.platform / command.account_id
        browser_result = self.browser.login(
            account_id=command.account_id,
            platform=self.platform,
            profile_dir=profile_dir,
            login_url=command.login_url,
            phone_number=command.phone_number,
            verification_code_provider=(
                self.verification_code_provider
                if command.phone_number is not None
                else None
            ),
            no_proxy=command.no_proxy,
            window_size=command.window_size,
            observe_code_button=command.observe_code_button,
        )
        status = browser_result.status or (
            "saved" if browser_result.success else "failed"
        )
        self.uow.accounts.add(Account(id=command.account_id, platform=self.platform))
        self.uow.auth_profiles.add(
            AccountAuthProfile(
                account_id=command.account_id,
                platform=self.platform,
                profile_dir=profile_dir,
                login_url=command.login_url,
                last_login_at=self.clock.now(),
                status=status,
                failure_reason=browser_result.failure_reason,
            )
        )
        self.uow.commit()
        return LoginXhsAccountResult(
            account_id=command.account_id,
            platform=self.platform,
            profile_dir=profile_dir,
            status=status,
            failure_reason=browser_result.failure_reason,
        )


@dataclass(frozen=True, slots=True)
class EnterLiveRoomHandler:
    """Dispatch an authorized account into a live room."""

    uow: UnitOfWork
    automation: LiveRoomAutomationPort
    clock: Clock
    ids: IdGenerator
    scheduler: AccountSchedulingService = AccountSchedulingService()

    def handle(self, command: EnterLiveRoomCommand) -> EnterLiveRoomResult:
        """Enter the live room and record a waiting or failed session."""
        account = self.uow.accounts.get(command.account_id)
        if account is None:
            raise EntityNotFound(f"account {command.account_id!r} was not found")

        room = LiveRoom(url=command.room_url, platform=command.platform)
        self.scheduler.ensure_can_enter(account=account, room=room)

        session_id = self.ids.new_id("session")
        entered_at = self.clock.now()
        automation_result = self.automation.enter_room(account=account, room=room)

        if automation_result.success:
            session = LiveRoomSession.waiting(
                id=session_id,
                account_id=account.id,
                room_url=room.url,
                platform=room.platform,
                entered_at=entered_at,
            )
        else:
            session = LiveRoomSession.enter_failed(
                id=session_id,
                account_id=account.id,
                room_url=room.url,
                platform=room.platform,
                entered_at=entered_at,
                failure_reason=automation_result.failure_reason or "enter room failed",
            )

        self.uow.sessions.add(session)
        self.uow.commit()
        return EnterLiveRoomResult(
            session_id=session.id,
            status=session.status,
            failure_reason=session.failure_reason,
        )


@dataclass(frozen=True, slots=True)
class SendCommentHandler:
    """Dispatch a comment from an account already waiting in the room."""

    uow: UnitOfWork
    automation: LiveRoomAutomationPort
    clock: Clock
    ids: IdGenerator
    policy: CommentDispatchPolicy = CommentDispatchPolicy()

    def handle(self, command: SendCommentCommand) -> SendCommentResult:
        """Send the comment and persist the dispatch record."""
        session = self.uow.sessions.get(command.session_id)
        if session is None:
            raise EntityNotFound(f"session {command.session_id!r} was not found")

        message = CommentMessage(command.text)
        self.policy.ensure_can_send(session=session)

        automation_result = self.automation.send_comment(
            session=session,
            text=message.text,
        )
        status = (
            CommentDispatchStatus.SENT
            if automation_result.success
            else CommentDispatchStatus.FAILED
        )
        dispatch = CommentDispatch(
            id=self.ids.new_id("dispatch"),
            session_id=session.id,
            account_id=session.account_id,
            text=message.text,
            status=status,
            sent_at=self.clock.now(),
            failure_reason=automation_result.failure_reason,
        )
        self.uow.comments.add(dispatch)
        self.uow.commit()
        return SendCommentResult(
            dispatch_id=dispatch.id,
            status=dispatch.status,
            failure_reason=dispatch.failure_reason,
        )
