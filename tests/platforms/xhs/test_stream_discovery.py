from __future__ import annotations

from smhelper.platforms.xhs.browser.stream_discovery import (
    XhsLiveRoomSignals,
    XhsLiveRoomStatus,
    is_xhs_stream_url,
    select_latest_stream_url,
)


def test_xhs_stream_url_detection_matches_flv_m3u8_and_live_source_play() -> None:
    assert is_xhs_stream_url("https://example.com/live.flv") is True
    assert is_xhs_stream_url("https://example.com/live.m3u8?token=1") is True
    assert is_xhs_stream_url("https://example.com/live-source-play?id=1") is True
    assert is_xhs_stream_url("https://example.com/image.jpg") is False


def test_select_latest_stream_url_returns_most_recent_candidate() -> None:
    assert (
        select_latest_stream_url(
            [
                "https://example.com/not-stream.jpg",
                "https://example.com/old.flv",
                "https://example.com/new.m3u8",
            ]
        )
        == "https://example.com/new.m3u8"
    )


def test_live_room_status_prefers_finished_signal_over_player_signal() -> None:
    signals = XhsLiveRoomSignals(
        finish_text="live ended",
        player_visible=True,
        video_visible=True,
        stream_url="https://example.com/live.flv",
    )

    assert XhsLiveRoomStatus.from_signals(signals) is XhsLiveRoomStatus.NOT_LIVE


def test_live_room_status_is_live_when_player_or_stream_url_is_visible() -> None:
    assert (
        XhsLiveRoomStatus.from_signals(
            XhsLiveRoomSignals(
                finish_text="",
                player_visible=True,
                video_visible=True,
                stream_url=None,
            )
        )
        is XhsLiveRoomStatus.LIVE
    )
    assert (
        XhsLiveRoomStatus.from_signals(
            XhsLiveRoomSignals(
                finish_text="",
                player_visible=False,
                video_visible=False,
                stream_url="https://example.com/live.flv",
            )
        )
        is XhsLiveRoomStatus.LIVE
    )
