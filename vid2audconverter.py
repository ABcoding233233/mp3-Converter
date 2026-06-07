import argparse
import importlib.util
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlparse


AUDIO_ONLY_FORMAT = "bestaudio[acodec!=none]/bestaudio"


def check_dependencies():
    """Check if required Python packages and executables are available."""
    missing_programs = []

    if importlib.util.find_spec("yt_dlp") is None:
        missing_programs.append("yt-dlp")

    if missing_programs:
        raise EnvironmentError(
            f"Required Python packages not found: {', '.join(missing_programs)}\n"
            "Install them with: uv pip install -r requirements.txt"
        )

    ffmpeg_location = shutil.which("ffmpeg") or get_bundled_ffmpeg()
    if not ffmpeg_location:
        raise EnvironmentError(
            "FFmpeg was not found in PATH and the bundled imageio-ffmpeg "
            "fallback is unavailable.\n"
            "Install dependencies with: uv pip install -r requirements.txt"
        )

    return {
        "yt_dlp_command": [sys.executable, "-m", "yt_dlp"],
        "ffmpeg_location": ffmpeg_location,
    }


def get_bundled_ffmpeg():
    """Return the imageio-ffmpeg executable path when available."""
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


def looks_like_playlist(source_url):
    """Return True when the URL has common YouTube playlist markers."""
    parsed = urlparse(source_url)
    query = parse_qs(parsed.query)

    return "list" in query or parsed.path.rstrip("/").endswith("/playlist")


def get_output_template(output_dir, playlist_mode):
    """Build a yt-dlp output template for single videos or playlists."""
    if playlist_mode:
        return str(
            output_dir
            / "%(playlist_title)s"
            / "%(playlist_index)03d - %(title)s.%(ext)s"
        )

    return str(output_dir / "%(title)s.%(ext)s")


def download_audio_as_mp3(source_url, output_dir, playlist_mode, dependencies):
    """Download audio-only media with yt-dlp and convert it to MP3."""
    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = get_output_template(output_dir, playlist_mode)

    command = list(dependencies["yt_dlp_command"])
    if playlist_mode:
        command.extend(["--yes-playlist", "--ignore-errors"])
    else:
        command.append("--no-playlist")

    command.extend(
        [
            "-f",
            AUDIO_ONLY_FORMAT,
            "-x",
            "--audio-format",
            "mp3",
            "--audio-quality",
            "2",
            "--embed-metadata",
            "--ffmpeg-location",
            dependencies["ffmpeg_location"],
            "--continue",
            "-o",
            output_template,
            source_url,
        ]
    )

    mode = "playlist" if playlist_mode else "single video"
    print(f"Downloading {mode} audio and converting to MP3...")
    print(f"Output folder: {output_dir}")

    subprocess.run(command, check=True)

    print(f"Done. MP3 file(s) saved under: {output_dir}")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Download YouTube audio as MP3 without downloading video streams."
    )
    parser.add_argument("url", nargs="?", help="YouTube video or playlist URL.")
    parser.add_argument(
        "-o",
        "--output-dir",
        help="Directory where MP3 files should be saved. Defaults to this script's folder.",
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
        help="Download only the single video, even if the URL contains playlist data.",
    )

    return parser.parse_args()


def main():
    print("Welcome to YouTube to MP3 Converter!")

    try:
        args = parse_args()
        dependencies = check_dependencies()

        source_url = args.url or input("Enter the YouTube URL: ").strip()
        if not source_url:
            print("Invalid URL. Please try again.")
            return

        if args.playlist:
            playlist_mode = True
        elif args.single:
            playlist_mode = False
        else:
            playlist_mode = looks_like_playlist(source_url)

        script_dir = Path(__file__).resolve().parent
        output_dir = (
            Path(args.output_dir).expanduser().resolve()
            if args.output_dir
            else script_dir
        )

        if playlist_mode:
            print("Playlist mode enabled.")
        else:
            print("Single-video mode enabled. Use --playlist to force playlist downloads.")

        download_audio_as_mp3(
            source_url=source_url,
            output_dir=output_dir,
            playlist_mode=playlist_mode,
            dependencies=dependencies,
        )

    except FileNotFoundError as e:
        print(f"File Error: {e}")
    except EnvironmentError as e:
        print(f"Environment Error: {e}")
    except subprocess.CalledProcessError as e:
        print(f"yt-dlp failed with exit code {e.returncode}.")
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Full error details:", str(sys.exc_info()))


if __name__ == "__main__":
    main()
