"""Unit tests for the pure helpers in vid2audconverter.

These cover URL classification and command/template building only, so they run
without a network connection, yt-dlp, or FFmpeg installed.

Run with:  pytest
"""

from pathlib import Path

from vid2audconverter import (
    SOURCE_FORMATS,
    build_item_command,
    build_yt_dlp_command,
    fetch_playlist_entries,
    get_item_output_template,
    get_output_template,
    looks_like_playlist,
    parse_progress_line,
    parse_flat_playlist_output,
    sanitize_filename,
)


FAKE_DEPS = {
    "yt_dlp_command": ["python", "-m", "yt_dlp"],
    "ffmpeg_location": "ffmpeg",
}


def test_bare_playlist_url_is_playlist():
    assert looks_like_playlist("https://www.youtube.com/playlist?list=PL123")


def test_watch_url_with_playlist_id_is_playlist():
    assert looks_like_playlist(
        "https://www.youtube.com/watch?v=Pi7l8mMjYVE"
        "&list=PLMrJAkhIeNNR20Mz-VpzgfQs5zrYi085m"
    )


def test_watch_url_with_mix_list_is_single():
    # Autoplay/radio links carry an RD-style list id but point at one video.
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


def test_item_command_uses_no_playlist_and_literal_index_prefix():
    command = build_item_command(
        "https://youtu.be/abc",
        Path("/music"),
        dependencies=FAKE_DEPS,
        quality={"source": "compact", "bitrate": 192},
        index=7,
    )
    output = command[command.index("-o") + 1]
    assert "--no-playlist" in command
    assert "--yes-playlist" not in command
    assert "007 - %(title)s.%(ext)s" in output
    assert command[command.index("--audio-quality") + 1] == "192K"
    assert command[-1] == "https://youtu.be/abc"


def test_item_template_sanitizes_playlist_subfolder():
    template = get_item_output_template(
        Path("/music"), index=3, playlist_title='Bad:Name*? '
    )
    assert "Bad_Name__" in template
    assert template.endswith("003 - %(title)s.%(ext)s")


def test_sanitize_filename_falls_back_for_empty_names():
    assert sanitize_filename(" . ") == "playlist"


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


def test_parse_flat_playlist_output_prefers_webpage_url():
    text = (
        "1\tFirst Song\thttps://youtu.be/abc\tabc\tMix Name\n"
        "2\tSecond Song\thttps://youtu.be/def\tdef\tMix Name\n"
    )
    entries, playlist_title = parse_flat_playlist_output(text)
    assert playlist_title == "Mix Name"
    assert entries == [
        (1, "First Song", "https://youtu.be/abc"),
        (2, "Second Song", "https://youtu.be/def"),
    ]


def test_parse_flat_playlist_output_falls_back_to_raw_url():
    text = "4\tFourth Song\tNA\thttps://youtu.be/four\tPlaylist\n"
    entries, playlist_title = parse_flat_playlist_output(text)
    assert playlist_title == "Playlist"
    assert entries == [(4, "Fourth Song", "https://youtu.be/four")]


def test_fetch_playlist_entries_forces_playlist_metadata(monkeypatch):
    captured = {}

    class FakeResult:
        stdout = "1\tSong\thttps://youtu.be/abc\tabc\tPlaylist\n"

    def fake_run(command, **kwargs):
        captured["command"] = command
        return FakeResult()

    monkeypatch.setattr("vid2audconverter.subprocess.run", fake_run)

    entries, playlist_title = fetch_playlist_entries(
        "https://www.youtube.com/watch?v=abc&list=PL123", FAKE_DEPS
    )

    assert "--yes-playlist" in captured["command"]
    assert entries == [(1, "Song", "https://youtu.be/abc")]
    assert playlist_title == "Playlist"
