import argparse
import importlib.util
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


# yt-dlp format selectors for the two source-quality choices.
SOURCE_FORMATS = {
    "best": "bestaudio[acodec!=none]/bestaudio",
    "compact": (
        "bestaudio[abr<=128][acodec!=none]/"
        "worstaudio[acodec!=none]/bestaudio"
    ),
}
BITRATE_CHOICES = [320, 256, 192, 128]
DEFAULT_QUALITY = {"source": "best", "bitrate": 320}

# Prefix that marks the progress lines emitted by --progress-template so the
# UI can tell them apart from normal yt-dlp output.
PROGRESS_SENTINEL = "@@PROG@@"

DOWNLOAD_PROGRESS_TEMPLATE = (
    f"download:{PROGRESS_SENTINEL}\tdownload\t"
    "%(info.playlist_index)s\t%(progress._percent_str)s\t"
    "%(progress.status)s"
)
CONVERT_PROGRESS_TEMPLATE = (
    f"postprocess:{PROGRESS_SENTINEL}\tconvert\t"
    "%(info.playlist_index)s\t-\t%(progress.status)s"
)

_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_PERCENT_RE = re.compile(r"(\d+(?:\.\d+)?)")
# Characters that are not allowed in Windows file/folder names.
_INVALID_FILENAME_RE = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
# YouTube generated mixes/radio queues use RD-style list ids. Keep those in
# single-video mode unless the user explicitly forces playlist mode.
_YOUTUBE_MIX_PLAYLIST_PREFIXES = ("RD",)


def main():
    args = parse_args()
    print("Welcome to YouTube to MP3 Converter!")

    try:
        dependencies = check_dependencies()
    except OSError as error:
        sys.exit(f"Environment error: {error}")

    source_url = args.url or input("Enter the YouTube URL: ").strip()
    if not source_url:
        sys.exit("No URL provided. Please try again.")

    playlist_mode = resolve_playlist_mode(args, source_url)
    output_dir = resolve_output_dir(args)

    if playlist_mode:
        print("Playlist mode enabled.")
    else:
        print("Single-video mode enabled.")
        print("Use --playlist to force playlist downloads.")

    quality = {"source": args.source, "bitrate": args.bitrate}

    try:
        download_audio_as_mp3(
            source_url=source_url,
            output_dir=output_dir,
            playlist_mode=playlist_mode,
            dependencies=dependencies,
            playlist_subfolder=args.subfolder,
            quality=quality,
        )
    except subprocess.CalledProcessError as error:
        sys.exit(f"yt-dlp failed with exit code {error.returncode}.")


def parse_args():
    """Parse command-line arguments for the CLI."""
    parser = argparse.ArgumentParser(
        description="Download YouTube audio as MP3 without downloading video."
    )
    parser.add_argument(
        "url", nargs="?", help="YouTube video or playlist URL."
    )
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Directory for the MP3 files. Defaults to this script's folder.",
    )

    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--playlist",
        action="store_true",
        help="Download every item in a playlist URL.",
    )
    mode.add_argument(
        "--single",
        action="store_true",
        help="Download only the single video, even if the URL has a playlist.",
    )

    parser.add_argument(
        "--subfolder",
        action="store_true",
        help="Save a playlist into a subfolder named after the playlist.",
    )
    parser.add_argument(
        "--bitrate",
        type=int,
        choices=BITRATE_CHOICES,
        default=DEFAULT_QUALITY["bitrate"],
        help="MP3 bitrate in kbps (default: 320).",
    )
    parser.add_argument(
        "--source",
        choices=list(SOURCE_FORMATS),
        default=DEFAULT_QUALITY["source"],
        help="Source audio: 'best' quality or 'compact' smaller download.",
    )

    return parser.parse_args()


def check_dependencies():
    """Return the yt-dlp command and FFmpeg path, or raise if missing."""
    if importlib.util.find_spec("yt_dlp") is None:
        raise OSError(
            "Required package yt-dlp was not found.\n"
            "Install it with: uv pip install -r requirements.txt"
        )

    ffmpeg_location = shutil.which("ffmpeg") or get_bundled_ffmpeg()
    if not ffmpeg_location:
        raise OSError(
            "FFmpeg was not found in PATH and the bundled imageio-ffmpeg "
            "fallback is unavailable.\n"
            "Install dependencies with: uv pip install -r requirements.txt"
        )

    return {
        "yt_dlp_command": [sys.executable, "-m", "yt_dlp"],
        "ffmpeg_location": ffmpeg_location,
    }


def get_bundled_ffmpeg():
    """Return the imageio-ffmpeg executable path when available, else None."""
    if importlib.util.find_spec("imageio_ffmpeg") is None:
        return None

    try:
        from imageio_ffmpeg import get_ffmpeg_exe
    except Exception:
        return None

    ffmpeg_path = Path(get_ffmpeg_exe())
    if ffmpeg_path.exists():
        return str(ffmpeg_path)

    return None


def resolve_playlist_mode(args, source_url):
    """Decide playlist vs single mode from the flags, else from the URL."""
    if args.playlist:
        return True
    if args.single:
        return False
    return looks_like_playlist(source_url)


def resolve_output_dir(args):
    """Return the output directory, defaulting to this script's folder."""
    if args.output_dir:
        return Path(args.output_dir).expanduser().resolve()
    return Path(__file__).resolve().parent


def looks_like_playlist(source_url):
    """Return True when the URL points at a playlist, not a single video."""
    parsed = urlparse(source_url)
    query = parse_qs(parsed.query)
    playlist_id = _first_real_value(*query.get("list", []))
    if not playlist_id:
        return False

    if parsed.path.rstrip("/").endswith("/playlist"):
        return True

    return not _looks_like_youtube_mix(playlist_id)


def _looks_like_youtube_mix(playlist_id):
    """Return True for generated YouTube mix/radio list ids."""
    normalized = playlist_id.upper()
    return normalized.startswith(_YOUTUBE_MIX_PLAYLIST_PREFIXES)


def download_audio_as_mp3(
    source_url,
    output_dir,
    playlist_mode,
    dependencies,
    playlist_subfolder=False,
    quality=None,
):
    """Download audio-only media with yt-dlp and convert it to MP3."""
    output_dir.mkdir(parents=True, exist_ok=True)
    command = build_yt_dlp_command(
        source_url=source_url,
        output_dir=output_dir,
        playlist_mode=playlist_mode,
        dependencies=dependencies,
        playlist_subfolder=playlist_subfolder,
        quality=quality,
    )

    mode = "playlist" if playlist_mode else "single video"
    print(f"Downloading {mode} audio and converting to MP3...")
    print(f"Output folder: {output_dir}")

    subprocess.run(command, check=True, env=utf8_subprocess_env())

    print(f"Done. MP3 file(s) saved under: {output_dir}")


def build_yt_dlp_command(
    source_url,
    output_dir,
    playlist_mode,
    dependencies,
    playlist_subfolder=False,
    quality=None,
):
    """Build the yt-dlp command used by both the CLI and desktop UI."""
    quality = quality or DEFAULT_QUALITY
    audio_format = SOURCE_FORMATS.get(
        quality["source"], SOURCE_FORMATS["best"]
    )
    output_template = get_output_template(
        output_dir, playlist_mode, playlist_subfolder
    )

    command = list(dependencies["yt_dlp_command"])
    if playlist_mode:
        command.extend(["--yes-playlist", "--ignore-errors"])
    else:
        command.append("--no-playlist")

    command.extend(_conversion_flags(audio_format, quality, dependencies))
    command.extend(["-o", output_template, source_url])
    return command


def build_item_command(
    item_url,
    output_dir,
    dependencies,
    quality=None,
    index=None,
    playlist_title=None,
):
    """Build a yt-dlp command that downloads+converts ONE video to MP3.

    Used by the desktop UI to run playlist tracks individually (in parallel).
    ``index`` prefixes the filename ("003 - Title.mp3") and ``playlist_title``,
    when given, nests the file in a subfolder of that (sanitized) name.
    """
    quality = quality or DEFAULT_QUALITY
    audio_format = SOURCE_FORMATS.get(
        quality["source"], SOURCE_FORMATS["best"]
    )
    output_template = get_item_output_template(
        output_dir, index, playlist_title
    )

    command = list(dependencies["yt_dlp_command"])
    command.append("--no-playlist")
    command.extend(_conversion_flags(audio_format, quality, dependencies))
    command.extend(["-o", output_template, item_url])
    return command


def _conversion_flags(audio_format, quality, dependencies):
    """Return the shared yt-dlp flags for audio-only download + MP3 convert."""
    return [
        "-f",
        audio_format,
        "-x",
        "--audio-format",
        "mp3",
        "--audio-quality",
        f"{quality['bitrate']}K",
        "--embed-metadata",
        "--newline",
        "--color",
        "never",
        "--progress-template",
        DOWNLOAD_PROGRESS_TEMPLATE,
        "--progress-template",
        CONVERT_PROGRESS_TEMPLATE,
        "--ffmpeg-location",
        dependencies["ffmpeg_location"],
        "--continue",
    ]


def get_output_template(output_dir, playlist_mode, playlist_subfolder=False):
    """Build a yt-dlp output template for single videos or playlists.

    Playlists land directly in ``output_dir`` unless ``playlist_subfolder`` is
    set, in which case they go into a subfolder named after the playlist.
    """
    if not playlist_mode:
        return str(output_dir / "%(title)s.%(ext)s")

    filename = "%(playlist_index)03d - %(title)s.%(ext)s"
    if playlist_subfolder:
        return str(output_dir / "%(playlist_title)s" / filename)
    return str(output_dir / filename)


def get_item_output_template(output_dir, index=None, playlist_title=None):
    """Output template for a single item downloaded with --no-playlist.

    The index (when known) is baked into the name as a literal prefix because
    --no-playlist means yt-dlp cannot fill %(playlist_index)s itself.
    """
    target_dir = output_dir
    if playlist_title:
        target_dir = output_dir / sanitize_filename(playlist_title)

    if index is not None:
        return str(target_dir / f"{index:03d} - %(title)s.%(ext)s")
    return str(target_dir / "%(title)s.%(ext)s")


def sanitize_filename(name):
    """Strip characters that are illegal in Windows file/folder names."""
    cleaned = _INVALID_FILENAME_RE.sub("_", name).strip().rstrip(". ")
    return cleaned or "playlist"


def parse_progress_line(line):
    """Parse a yt-dlp --progress-template line into a dict, else return None.

    Normal log lines (anything not prefixed with PROGRESS_SENTINEL) return
    None. A parsed line looks like::

        {"phase": "download"|"convert", "index": int|None,
         "percent": float|None, "status": "downloading"|"finished"|...}

    ``index`` is the 1-based playlist position, or None for a single video.
    """
    line = _ANSI_RE.sub("", line)
    if not line.startswith(PROGRESS_SENTINEL):
        return None

    parts = line.split("\t")
    if len(parts) < 5:
        return None

    _, phase, index_raw, percent_raw, status = parts[:5]
    return {
        "phase": phase,
        "index": _parse_index(index_raw),
        "percent": _parse_percent(percent_raw),
        "status": status.strip(),
    }


def _parse_index(raw):
    """Return a 1-based playlist index, or None when there isn't one."""
    raw = raw.strip()
    if raw.isdigit():
        return int(raw)
    return None


def _parse_percent(raw):
    """Return a float percentage from a string like ' 45.2%', else None."""
    match = _PERCENT_RE.search(raw)
    return float(match.group(1)) if match else None


def fetch_playlist_entries(source_url, dependencies):
    """Return ``(entries, playlist_title)`` for a playlist URL.

    ``entries`` is a list of ``(index, title, url)`` tuples; both are empty on
    failure. Uses a fast --flat-playlist metadata pass (no downloads) so the UI
    can show every track and download them individually.
    """
    command = list(dependencies["yt_dlp_command"]) + [
        "--yes-playlist",
        "--flat-playlist",
        "--no-warnings",
        "--print",
        (
            "%(playlist_index)s\t%(title)s\t%(webpage_url)s\t%(url)s\t"
            "%(playlist_title)s"
        ),
        source_url,
    ]

    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            env=utf8_subprocess_env(),
        )
    except Exception:
        return [], ""

    return parse_flat_playlist_output(result.stdout)


def parse_flat_playlist_output(text):
    """Parse --flat-playlist --print output into (entries, playlist_title)."""
    entries = []
    playlist_title = ""
    for line in text.splitlines():
        parts = line.split("\t")
        if len(parts) < 4:
            continue

        index = _parse_index(parts[0])
        if index is None:
            continue

        title = parts[1].strip() or f"Item {index}"
        url = _first_real_value(parts[2], parts[3])
        if not url:
            continue
        if len(parts) >= 5 and parts[4].strip():
            playlist_title = parts[4].strip()
        entries.append((index, title, url))

    return entries, playlist_title


def _first_real_value(*values):
    """Return the first non-empty yt-dlp value that is not the NA sentinel."""
    for value in values:
        value = value.strip()
        if value and value != "NA":
            return value
    return ""


def utf8_subprocess_env():
    """Return an environment that forces UTF-8 I/O for the yt-dlp subprocess.

    Without this, video titles containing non-ASCII characters can raise
    UnicodeEncodeError on legacy Windows consoles (cp1252).
    """
    env = os.environ.copy()
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


if __name__ == "__main__":
    main()
