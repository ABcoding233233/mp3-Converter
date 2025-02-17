# YouTube to MP3 Converter

This script downloads YouTube videos and converts them to MP3 files using [yt-dlp](https://github.com/yt-dlp/yt-dlp).

## Features
- Downloads videos and extracts audio in MP3 format.
- Supports interactive mode (single video) and batch mode (read URLs from a file).
- Validates YouTube URLs.

## Requirements
- Python 3.6+
- [yt-dlp](https://github.com/yt-dlp/yt-dlp) installed and added to your system's PATH.

## Installation
1. Clone the repository.
2. Install the required dependencies.
   ```bash
   pip install -r requirements.txt  # if a requirements file is provided
   ```
3. Ensure `yt-dlp` is installed:
   ```bash
   pip install yt-dlp
   ```

## Usage

### Interactive Mode
Run the script without arguments to input a YouTube URL manually:
