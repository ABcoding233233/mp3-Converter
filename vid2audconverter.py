import subprocess
import os
import shutil
import sys
import tempfile
from urllib.parse import urlparse
import argparse
from typing import Set, List

def check_dependencies():
    """Check if required programs are available in PATH."""
    missing_programs = []
    for program in ["yt-dlp"]:  # Removed ffmpeg as it's no longer needed
        if not shutil.which(program):
            missing_programs.append(program)
    
    if missing_programs:
        raise EnvironmentError(
            f"Required programs not found in PATH: {', '.join(missing_programs)}\n"
            "Please ensure they are installed and added to your system's PATH."
        )

def get_video_title(youtube_url):
    """Extract the video title from the YouTube URL using yt-dlp."""
    try:
        yt_dlp_path = shutil.which("yt-dlp")
        result = subprocess.run(
            [yt_dlp_path, "--get-title", youtube_url],
            check=True,
            capture_output=True,
            text=True
        )
        title = result.stdout.strip()
        # Remove invalid characters for filenames
        valid_chars = "-_.() abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
        title = "".join(c for c in title if c in valid_chars)
        return title
    except subprocess.CalledProcessError as e:
        print(f"Error fetching video title: {e.stderr}")
        return "video"  # Fallback to a default name

def download_audio(youtube_url, output_audio):
    """Download and convert to MP3 using yt-dlp."""
    try:
        print(f"Downloading and converting to MP3: {output_audio}")
        yt_dlp_path = shutil.which("yt-dlp")

        # Generate a temp path without creating the file
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, f"temp_audio_{os.getpid()}.%(ext)s")

        result = subprocess.run(
            [
                yt_dlp_path,
                "--rm-cache-dir",
                "--add-header", "User-Agent: Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
                "-x",  # Extract audio
                "--audio-format", "mp3",  # Convert to MP3
                "--audio-quality", "0",  # Best quality
                "-o", temp_file_path,
                youtube_url
            ],
            check=True,
            capture_output=True,
            text=True
        )

        # Find the actual downloaded file
        downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(f"temp_audio_{os.getpid()}")]
        if not downloaded_files:
            raise FileNotFoundError("Downloaded file not found in temp directory")
        
        temp_file_path = os.path.join(temp_dir, downloaded_files[0])
        shutil.move(temp_file_path, output_audio)

        if os.path.exists(output_audio):
            print("Audio downloaded and converted successfully.")
        else:
            print("Error: Audio file not created after download.")
            print("yt-dlp output:", result.stdout)
            print("yt-dlp error output:", result.stderr)
            raise FileNotFoundError("Downloaded audio file not found")

    except subprocess.CalledProcessError as e:
        print(f"Error downloading audio: {e.stderr}")
        print("yt-dlp output:", e.stdout)
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        raise

def is_valid_youtube_url(url: str) -> bool:
    """Validate if the URL is a YouTube URL."""
    try:
        parsed = urlparse(url)
        return "youtube.com" in parsed.netloc or "youtu.be" in parsed.netloc
    except:
        return False

def process_url_file(file_path: str) -> Set[str]:
    """Read and validate URLs from a file, returning unique valid URLs."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"File not found: {file_path}")
    
    unique_urls = set()
    invalid_urls = []
    
    with open(file_path, 'r') as f:
        urls = [line.strip() for line in f if line.strip()]
    
    for url in urls:
        if is_valid_youtube_url(url):
            unique_urls.add(url)
        else:
            invalid_urls.append(url)
    
    print(f"\nFound {len(unique_urls)} valid unique YouTube URLs")
    if invalid_urls:
        print(f"Skipping {len(invalid_urls)} invalid URLs")
    
    return unique_urls

def batch_download(urls: Set[str]) -> List[tuple]:
    """Download multiple URLs and return results."""
    results = []
    total = len(urls)
    
    print(f"\nStarting batch download of {total} videos...")
    for i, url in enumerate(urls, 1):
        try:
            print(f"\nProcessing {i}/{total}: {url}")
            title = get_video_title(url)
            output_path = os.path.join(os.path.dirname(__file__), f"{title}.mp3")
            download_audio(url, output_path)
            results.append((url, True, None))
        except Exception as e:
            results.append((url, False, str(e)))
    
    return results

def main():
    parser = argparse.ArgumentParser(description='YouTube to MP3 Converter')
    parser.add_argument('-f', '--file', help='Text file containing YouTube URLs (one per line)')
    args = parser.parse_args()

    try:
        check_dependencies()
        
        if args.file:
            # Batch processing mode
            urls = process_url_file(args.file)
            if not urls:
                print("No valid URLs found in file.")
                return
            
            results = batch_download(urls)
            
            # Summary
            success = sum(1 for _, success, _ in results if success)
            print("\nDownload Summary:")
            print(f"Successfully downloaded: {success}/{len(results)}")
            
            # Print failures if any
            failures = [(url, error) for url, success, error in results if not success]
            if failures:
                print("\nFailed downloads:")
                for url, error in failures:
                    print(f"- {url}: {error}")
            
        else:
            # Original interactive mode
            youtube_url = input("Enter the YouTube URL: ").strip()
            if not youtube_url:
                print("Invalid URL. Please try again.")
                return

            video_title = get_video_title(youtube_url)
            print(f"Video title: {video_title}")

            script_dir = os.path.abspath(os.path.dirname(__file__))
            output_audio = os.path.join(script_dir, f"{video_title}.mp3")
            
            print(f"\nCurrent working directory: {os.getcwd()}")
            print(f"Audio will be saved to: {output_audio}\n")

            download_audio(youtube_url, output_audio)

    except FileNotFoundError as e:
        print(f"File Error: {e}")
    except EnvironmentError as e:
        print(f"Environment Error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Full error details:", str(sys.exc_info()))

if __name__ == "__main__":
    main()