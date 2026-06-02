"""SQLAdmin setup and first-phase single-admin authentication."""

from __future__ import annotations

from dataclasses import dataclass
from hmac import compare_digest
from os import getenv

from fastapi import FastAPI
from sqlalchemy import Engine
from sqladmin import Admin
from sqladmin.authentication import AuthenticationBackend
from starlette.requests import Request
from starlette.responses import Response

from smhelper.web.admin_views.accounts import (
    AccountAuthStateAdmin,
    PlatformAccountAdmin,
)
from smhelper.web.admin_views.candidates import (
    CandidateDispatcher,
    CandidateQuestionAdmin,
    CandidateReviewer,
)
from smhelper.web.admin_views.dispatch_jobs import DispatchJobAdmin, SendAttemptAdmin
from smhelper.web.admin_views.live_tasks import LiveTaskAdmin, LiveTaskObserverPublisher
from smhelper.web.admin_views.sessions import AccountLiveSessionAdmin
from smhelper.web.admin_views.workers import WorkerNodeAdmin


@dataclass(frozen=True, slots=True)
class AdminCredentials:
    """Credentials for the first-phase single SQLAdmin user."""

    username: str
    password: str
    secret_key: str

    @classmethod
    def from_env(cls) -> AdminCredentials:
        """Load credentials from environment variables with development defaults."""
        return cls(
            username=getenv("SMHELPER_ADMIN_USERNAME", "admin"),
            password=getenv("SMHELPER_ADMIN_PASSWORD", "admin"),
            secret_key=getenv("SMHELPER_ADMIN_SECRET_KEY", "dev-secret-change-me"),
        )


class SingleAdminAuth(AuthenticationBackend):
    """SQLAdmin authentication backend for a single configured administrator."""

    def __init__(self, credentials: AdminCredentials) -> None:
        super().__init__(secret_key=credentials.secret_key)
        self._credentials = credentials

    async def login(self, request: Request) -> bool:
        """Validate the login form and store the admin identity in the session."""
        form = await request.form()
        username = str(form.get("username", ""))
        password = str(form.get("password", ""))
        if not (
            compare_digest(username, self._credentials.username)
            and compare_digest(password, self._credentials.password)
        ):
            return False
        request.session["admin_user"] = self._credentials.username
        return True

    async def logout(self, request: Request) -> Response | bool:
        """Clear the admin session."""
        request.session.clear()
        return True

    async def authenticate(self, request: Request) -> Response | bool:
        """Return whether the request is already authenticated."""
        return request.session.get("admin_user") == self._credentials.username


def configure_admin(
    *,
    app: FastAPI,
    engine: Engine,
    credentials: AdminCredentials,
    candidate_dispatcher: CandidateDispatcher | None = None,
    candidate_reviewer: CandidateReviewer | None = None,
    live_task_observer_publisher: LiveTaskObserverPublisher | None = None,
    center_queue_name: str = "center.live",
) -> Admin:
    """Attach SQLAdmin to the FastAPI app and register first-phase views."""
    CandidateQuestionAdmin.candidate_dispatcher = candidate_dispatcher
    CandidateQuestionAdmin.candidate_reviewer = candidate_reviewer
    LiveTaskAdmin.observer_publisher = live_task_observer_publisher
    LiveTaskAdmin.center_queue_name = center_queue_name
    admin = Admin(
        app=app,
        engine=engine,
        title="smhelper",
        authentication_backend=SingleAdminAuth(credentials),
    )
    admin.add_view(PlatformAccountAdmin)
    admin.add_view(AccountAuthStateAdmin)
    admin.add_view(WorkerNodeAdmin)
    admin.add_view(LiveTaskAdmin)
    admin.add_view(CandidateQuestionAdmin)
    admin.add_view(AccountLiveSessionAdmin)
    admin.add_view(DispatchJobAdmin)
    admin.add_view(SendAttemptAdmin)
    app.state.admin = admin
    return admin
