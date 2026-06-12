# YouTube to MP3 Converter

A simple command-line tool that uses `yt-dlp` and FFmpeg to download YouTube audio streams and convert them to MP3.

## Features

- Downloads audio-only streams when available instead of downloading the full video first.
- Converts downloaded audio to MP3 with FFmpeg through `yt-dlp`.
- Supports single videos and full playlists.
- Selectable quality: source audio (best or compact) and MP3 bitrate (320/256/192/128 kbps).
- Desktop queue UI with live per-track progress and expandable playlist rows.
- Known playlist tracks run in a small parallel worker pool for faster batches.
- Playlists save directly into your chosen folder, or into a per-playlist subfolder if you ask.

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

Launch the desktop UI:

```powershell
.\.venv\Scripts\python.exe mp3_converter_ui.py
```

You can also run without activating the virtual environment:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = ".uv-python"
uv run --with-requirements requirements.txt python vid2audconverter.py --help
```

Launch the desktop UI with `uv run`:

```powershell
$env:UV_CACHE_DIR = ".uv-cache"
$env:UV_PYTHON_INSTALL_DIR = ".uv-python"
uv run --with-requirements requirements.txt python mp3_converter_ui.py
```

## Usage

### Desktop UI

```powershell
.\.venv\Scripts\python.exe mp3_converter_ui.py
```

Paste one or more YouTube links, choose Auto, Single, or Playlist mode, pick the **Source** and **Bitrate** quality, select an output folder, then start the queue. Each row shows live progress; playlists expand into one row per track, each with its own progress, and the playlist row shows an overall `45% (3/12)` summary. When the app can fetch the playlist track list first, it processes up to three tracks at once. Tick **Playlist subfolder** to group a playlist's tracks into a folder named after the playlist (off by default - tracks go straight into the chosen folder).

### Command Line

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

Mode is chosen automatically when you don't pass `--playlist` or `--single`:

- A dedicated playlist URL (`.../playlist?list=...`) downloads the whole playlist.
- A watch URL with a normal playlist id (`.../watch?v=...&list=PL...`) downloads the whole playlist.
- A watch URL with a YouTube mix/radio id (`...&list=RD...`) is treated as a single video so you do not accidentally pull a generated queue. Pass `--playlist` to force the full list.

Save output to a different folder:

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py --playlist -o "D:\Music\YouTube" "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

Playlist files are saved **directly** in the output folder (`01 - Title.mp3`, `02 - Title.mp3`, …). Pass `--subfolder` to group them into a subfolder named after the playlist instead:

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py --playlist --subfolder -o "D:\Music" "https://www.youtube.com/playlist?list=PLAYLIST_ID"
```

Choose quality with `--bitrate` (320, 256, 192, or 128 kbps; default 320) and `--source` (`best` audio, or `compact` for a smaller download before conversion):

```powershell
.\.venv\Scripts\python.exe vid2audconverter.py --bitrate 192 --source compact "https://www.youtube.com/watch?v=VIDEO_ID"
```

## Running Tests

The URL-classification and command-building helpers have `pytest` tests that run offline (no network, yt-dlp, or FFmpeg needed):

```powershell
.\.venv\Scripts\python.exe -m pytest
```

## Notes

The script avoids downloading video streams by using `yt-dlp`'s audio-only format selector. It still downloads the selected audio file before FFmpeg converts that audio file to MP3, which is how `yt-dlp -x` works.

In playlist mode the script passes `--ignore-errors` so one unavailable video doesn't abort the whole list. When that happens the UI marks the job **Partial** instead of **Done**, and the failing items are visible in the log.
