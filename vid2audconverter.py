import subprocess
import os
import shutil
import sys
import tempfile

def check_dependencies():
    """Check if required programs are available in PATH."""
    missing_programs = []
    for program in ["yt-dlp", "ffmpeg"]:
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

def download_video(youtube_url, output_video):
    """Download video using yt-dlp."""
    try:
        print(f"Downloading video to: {output_video}")
        yt_dlp_path = shutil.which("yt-dlp")

        # Generate a temp path without creating the file
        temp_dir = tempfile.gettempdir()
        temp_file_path = os.path.join(temp_dir, f"temp_video_{os.getpid()}.%(ext)s")

        result = subprocess.run(
            [
                yt_dlp_path,
                "-f", "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
                "--remux-video", "mp4",
                "-o", temp_file_path,
                youtube_url
            ],
            check=True,
            capture_output=True,
            text=True
        )

        # Find the actual downloaded file
        downloaded_files = [f for f in os.listdir(temp_dir) if f.startswith(f"temp_video_{os.getpid()}")]
        if not downloaded_files:
            raise FileNotFoundError("Downloaded file not found in temp directory")
        
        temp_file_path = os.path.join(temp_dir, downloaded_files[0])
        shutil.move(temp_file_path, output_video)

        if os.path.exists(output_video):
            print("Video downloaded successfully.")
        else:
            print("Error: Video file not created after download.")
            print("yt-dlp output:", result.stdout)
            print("yt-dlp error output:", result.stderr)
            raise FileNotFoundError("Downloaded video file not found")

    except subprocess.CalledProcessError as e:
        print(f"Error downloading video: {e.stderr}")
        print("yt-dlp output:", e.stdout)
        raise
    except Exception as e:
        print(f"An unexpected error occurred: {str(e)}")
        raise

def is_video_valid(video_file):
    """Check if the video file is valid using FFmpeg."""
    try:
        result = subprocess.run(
            ["ffmpeg", "-v", "error", "-i", video_file, "-f", "null", "-"],
            capture_output=True,
            text=True
        )
        return result.returncode == 0
    except Exception as e:
        print(f"Error validating video: {str(e)}")
        return False

def convert_to_mp3(input_video, output_audio):
    """Convert video to MP3 using FFmpeg."""
    try:
        if not os.path.exists(input_video):
            raise FileNotFoundError(f"Input video file not found: {input_video}")
        
        print(f"Converting video to MP3...")
        print(f"Input file: {input_video}")
        print(f"Output file: {output_audio}")
        
        ffmpeg_path = shutil.which("ffmpeg")
        result = subprocess.run(
            [
                ffmpeg_path,
                "-y",  # Overwrite output file if exists
                "-i", input_video,
                "-vn",  # Disable video
                "-acodec", "libmp3lame",
                "-q:a", "2",
                "-id3v2_version", "3",  # Better metadata support
                output_audio
            ],
            check=True,
            capture_output=True,
            text=True
        )
        
        if os.path.exists(output_audio):
            print(f"Conversion complete! MP3 saved as: {output_audio}")
        else:
            print("Error: MP3 file not created after conversion")
            print("FFmpeg output:", result.stdout)
            raise FileNotFoundError("Output MP3 file not found")
            
    except subprocess.CalledProcessError as e:
        print(f"Error converting to MP3: {e.stderr}")
        raise

def main():
    print("Welcome to YouTube to MP3 Converter!")
    
    try:
        # First check if required programs are available
        check_dependencies()
        
        youtube_url = input("Enter the YouTube URL: ").strip()
        if not youtube_url:
            print("Invalid URL. Please try again.")
            return

        # Get the video title
        video_title = get_video_title(youtube_url)
        print(f"Video title: {video_title}")

        # Get the script's directory
        script_dir = os.path.abspath(os.path.dirname(__file__))
        
        # Create absolute paths for output files using the video title
        output_video = os.path.join(script_dir, f"{video_title}.mp4")
        output_audio = os.path.join(script_dir, f"{video_title}.mp3")
        
        # Print working directory and file paths
        print(f"\nCurrent working directory: {os.getcwd()}")
        print(f"Video will be saved to: {output_video}")
        print(f"Audio will be saved to: {output_audio}\n")

        # Step 1: Download the video
        download_video(youtube_url, output_video)
        
        # Step 2: Validate the downloaded video
        print("Validating downloaded video...")
        if not is_video_valid(output_video):
            os.remove(output_video)
            raise ValueError("Downloaded video file is corrupted or invalid")
        
        # Step 3: Convert to MP3
        convert_to_mp3(output_video, output_audio)
        
        # Optional: Remove the video file to save space
        if os.path.exists(output_video):
            os.remove(output_video)
            print(f"Temporary video file {output_video} deleted.")
            
    except FileNotFoundError as e:
        print(f"File Error: {e}")
    except EnvironmentError as e:
        print(f"Environment Error: {e}")
    except Exception as e:
        print(f"An error occurred: {e}")
        print("Full error details:", str(sys.exc_info()))

if __name__ == "__main__":
    main()