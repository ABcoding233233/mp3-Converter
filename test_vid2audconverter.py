"""Unit tests for the pure helpers in vid2audconverter.

These cover URL classification and command/template building only, so they run
without a network connection, yt-dlp, or FFmpeg installed.

Run with:  pytest
"""

from pathlib import Path

from vid2audconverter import (
    SOURCE_FORMATS,
    build_yt_dlp_command,
    get_output_template,
    looks_like_playlist,
    parse_progress_line,
)


FAKE_DEPS = {
    "yt_dlp_command": ["python", "-m", "yt_dlp"],
    "ffmpeg_location": "ffmpeg",
}


def test_bare_playlist_url_is_playlist():
    assert looks_like_playlist("https://www.youtube.com/playlist?list=PL123")


def test_watch_url_with_list_is_single():
    # Autoplay/radio links carry a list= but point at one video.
    assert not looks_like_playlist(
        "https://www.youtube.com/watch?v=abc123&list=RD123"
    )


def test_plain_watch_url_is_single():
    assert not looks_like_playlist("https://www.youtube.com/watch?v=abc123")


def test_short_youtu_be_url_is_single():
    assert not looks_like_playlist("https://youtu.be/abc123")


def test_short_youtu_be_url_with_list_is_single():
    assert not looks_like_playlist("https://youtu.be/abc123?list=RD123")


def test_single_template():
    template = get_output_template(Path("/music"), playlist_mode=False)
    assert template.endswith("%(title)s.%(ext)s")
    assert "playlist_index" not in template


def test_playlist_template_has_no_subfolder_by_default():
    template = get_output_template(Path("/music"), playlist_mode=True)
    assert "%(playlist_index)03d" in template
    assert "%(playlist_title)s" not in template


def test_playlist_template_with_subfolder():
    template = get_output_template(
        Path("/music"), playlist_mode=True, playlist_subfolder=True
    )
    assert "%(playlist_title)s" in template
    assert "%(playlist_index)03d" in template


def test_single_command_uses_no_playlist():
    command = build_yt_dlp_command(
        "https://youtu.be/abc",
        Path("/music"),
        playlist_mode=False,
        dependencies=FAKE_DEPS,
    )
    assert "--no-playlist" in command
    assert "--yes-playlist" not in command


def test_playlist_command_uses_yes_playlist_and_ignore_errors():
    command = build_yt_dlp_command(
        "https://www.youtube.com/playlist?list=PL123",
        Path("/music"),
        playlist_mode=True,
        dependencies=FAKE_DEPS,
    )
    assert "--yes-playlist" in command
    assert "--ignore-errors" in command


def test_command_extracts_audio_only_mp3():
    command = build_yt_dlp_command(
        "https://youtu.be/abc",
        Path("/music"),
        playlist_mode=False,
        dependencies=FAKE_DEPS,
    )
    assert "-x" in command
    assert SOURCE_FORMATS["best"] in command
    # The audio format mp3 immediately follows the --audio-format flag.
    assert command[command.index("--audio-format") + 1] == "mp3"
    # The URL is always the final positional argument.
    assert command[-1] == "https://youtu.be/abc"


def test_default_quality_is_320k_best():
    command = build_yt_dlp_command(
        "https://youtu.be/abc",
        Path("/music"),
        playlist_mode=False,
        dependencies=FAKE_DEPS,
    )
    assert command[command.index("--audio-quality") + 1] == "320K"
    assert SOURCE_FORMATS["best"] in command


def test_quality_overrides_source_and_bitrate():
    command = build_yt_dlp_command(
        "https://youtu.be/abc",
        Path("/music"),
        playlist_mode=False,
        dependencies=FAKE_DEPS,
        quality={"source": "compact", "bitrate": 128},
    )
    assert command[command.index("--audio-quality") + 1] == "128K"
    assert SOURCE_FORMATS["compact"] in command


def test_parse_progress_download_with_index():
    line = "@@PROG@@\tdownload\t3\t 45.2%\tdownloading"
    result = parse_progress_line(line)
    assert result == {
        "phase": "download",
        "index": 3,
        "percent": 45.2,
        "status": "downloading",
    }


def test_parse_progress_convert_finished_single_video():
    line = "@@PROG@@\tconvert\tNA\t-\tfinished"
    result = parse_progress_line(line)
    assert result["phase"] == "convert"
    assert result["index"] is None
    assert result["status"] == "finished"


def test_parse_progress_ignores_normal_log_lines():
    assert parse_progress_line("[download] Destination: song.webm") is None
    assert parse_progress_line("ERROR: video unavailable") is None
