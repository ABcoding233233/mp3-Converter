# YouTube to MP3 Converter

A simple command-line tool that uses `yt-dlp` and FFmpeg to download YouTube audio streams and convert them to MP3.

## Features

- Downloads audio-only streams when available instead of downloading the full video first.
- Converts downloaded audio to MP3 with FFmpeg through `yt-dlp`.
- Supports single videos and full playlists.
- Saves playlist downloads into a folder named after the playlist.

## Requirements

Install [uv](https://docs.astral.sh/uv/). The repo dependencies are listed in `requirements.txt`:

- [yt-dlp](https://github.com/yt-dlp/yt-dlp)
- [imageio-ffmpeg](https://github.com/imageio/imageio-ffmpeg)

If FFmpeg is already available in PATH, the script will use it. Otherwise, `imageio-ffmpeg` provides a bundled FFmpeg executable for MP3 conversion.

## Installation With uv

From the repo root:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = ".uv-python"
uv venv
uv pip install -r requirements.txt
```

Check that the script starts:

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py --help
```

You can also run without activating the virtual environment:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = ".uv-python"
uv run --with-requirements requirements.txt python vid2audconverter.py --help
```

## Usage

Run interactively:

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py
```

Download one video:

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py "https://www.youtube.com/watch?v=VIDEO_ID"
```

Download an entire playlist:

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py --playlist "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

If the URL already contains a YouTube `list=` parameter, playlist mode is enabled automatically. Use `--single` to download only the video from a URL that also contains playlist data.

Save output to a different folder:

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py --playlist -o "D:\Music\YouTube" "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

## Notes

The script avoids downloading video streams by using `yt-dlp`'s audio-only format selector. It still downloads the selected audio file before FFmpeg converts that audio file to MP3, which is how `yt-dlp -x` works.
