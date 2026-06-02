"""Celery task names shared by center and worker nodes."""

from __future__ import annotations

ENTER_LIVE_ROOM_TASK = "smhelper.node.enter_live_room"
SEND_COMMENT_TASK = "smhelper.node.send_comment"
CLOSE_SESSION_TASK = "smhelper.node.close_session"
PROCESS_SEGMENT_TASK = "smhelper.center.process_segment"
GENERATE_CANDIDATE_TASK = "smhelper.center.generate_candidate"
OBSERVE_LIVE_TASK_TASK = "smhelper.center.observe_live_task"
