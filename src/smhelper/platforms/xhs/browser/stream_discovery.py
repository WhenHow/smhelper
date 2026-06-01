"""Xiaohongshu live-room stream URL and status semantics."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class XhsLiveRoomStatus(str, Enum):
    """Observed Xiaohongshu live-room status."""

    LIVE = "live"
    NOT_LIVE = "not_live"
    UNKNOWN = "unknown"

    @classmethod
    def from_signals(cls, signals: "XhsLiveRoomSignals") -> XhsLiveRoomStatus:
        """Infer live-room status from page signals."""
        if _is_finished_text(signals.finish_text):
            return cls.NOT_LIVE
        if signals.player_visible and signals.video_visible:
            return cls.LIVE
        if signals.stream_url is not None and is_xhs_stream_url(signals.stream_url):
            return cls.LIVE
        return cls.UNKNOWN


@dataclass(frozen=True, slots=True)
class XhsLiveRoomSignals:
    """Page signals used by the center observer."""

    finish_text: str
    player_visible: bool
    video_visible: bool
    stream_url: str | None


def is_xhs_stream_url(url: str) -> bool:
    """Return whether a resource URL looks like an XHS live media stream."""
    lowered = url.lower()
    return ".flv" in lowered or ".m3u8" in lowered or "live-source-play" in lowered


def select_latest_stream_url(resource_urls: list[str]) -> str | None:
    """Return the newest stream-looking resource URL."""
    for url in reversed(resource_urls):
        if is_xhs_stream_url(url):
            return url
    return None


def _is_finished_text(text: str) -> bool:
    normalized = text.strip().lower()
    return "live ended" in normalized or "直播已结束" in normalized
