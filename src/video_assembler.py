"""
Video Assembler — Combines podcast audio with B-roll clips using FFmpeg.
Renders a 1920x1080 landscape video with text overlay.
"""
import os
import subprocess
import logging
import json

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)


def _get_video_duration(video_path):
    """Get duration of a video file using ffprobe."""
    try:
        cmd = [
            "ffprobe", "-v", "quiet", "-print_format", "json",
            "-show_format", video_path
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception as e:
        logger.warning(f"Could not probe duration for {video_path}: {e}")
        return 5.0  # Default 5 seconds


def _build_concat_list(broll_paths, target_duration):
    """
    Build a concat list file that loops B-roll clips to match the target audio duration.
    Returns path to the concat list file.
    """
    concat_path = os.path.join(OUTPUT_DIR, "broll_concat.txt")

    # Get durations of all clips
    clip_durations = []
    for path in broll_paths:
        dur = _get_video_duration(path)
        clip_durations.append((path, dur))

    if not clip_durations:
        logger.error("No B-roll clips available for concatenation")
        return None

    # Build the concat list, looping clips until we exceed the target duration
    total = 0.0
    entries = []
    idx = 0
    while total < target_duration:
        path, dur = clip_durations[idx % len(clip_durations)]
        # FFmpeg concat demuxer requires forward slashes and escaped quotes
        safe_path = path.replace("\\", "/")
        entries.append(f"file '{safe_path}'")
        total += dur
        idx += 1

        # Safety: don't loop more than 200 times
        if idx > 200:
            break

    with open(concat_path, "w", encoding="utf-8") as f:
        f.write("\n".join(entries))

    logger.info(
        f"📋 Concat list: {len(entries)} entries, "
        f"estimated {total:.1f}s (target: {target_duration:.1f}s)"
    )
    return concat_path


def assemble(audio_data, broll_paths, script_data, language="english"):
    """
    Assemble the final video by combining audio with B-roll.

    Args:
        audio_data: dict with "path" and "duration_seconds"
        broll_paths: list of local B-roll video file paths
        script_data: dict with "title"
        language: "english" or "tamil"

    Returns:
        str: path to the final video file, or None on failure
    """
    audio_path = audio_data["path"]
    audio_duration = audio_data["duration_seconds"]
    title = script_data.get("title", "Market Analysis")

    output_path = os.path.join(OUTPUT_DIR, f"longform_{language}.mp4")

    logger.info(f"🎞️  Assembling {language.upper()} video ({audio_duration:.0f}s)...")

    if not broll_paths:
        logger.error("No B-roll clips provided. Cannot assemble video.")
        return None

    # Build concat list
    concat_path = _build_concat_list(broll_paths, audio_duration)
    if not concat_path:
        return None

    # Escape special characters in title for FFmpeg drawtext
    safe_title = title.replace("'", "'\\''").replace(":", " -")[:60]

    # FFmpeg command:
    # 1. Concatenate B-roll clips
    # 2. Scale to 1920x1080
    # 3. Trim to match audio duration
    # 4. Overlay audio
    # 5. Add subtle bottom text bar
    cmd = [
        "ffmpeg", "-y",
        # Input 1: B-roll video concat
        "-f", "concat", "-safe", "0", "-i", concat_path,
        # Input 2: Podcast audio
        "-i", audio_path,
        # Video filter: scale + crop to 1080p, add text overlay
        "-filter_complex",
        (
            "[0:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "setsar=1[scaled];"
            "[scaled]drawtext="
            "text='Market Debunk Podcast':"
            "fontsize=28:fontcolor=white@0.8:"
            "x=(w-text_w)/2:y=h-60:"
            "box=1:boxcolor=black@0.5:boxborderw=8[out]"
        ),
        "-map", "[out]",
        "-map", "1:a",
        # Duration: match audio exactly
        "-t", str(audio_duration),
        # Output settings
        "-c:v", "libx264", "-preset", "medium", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-r", "30",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
        output_path,
    ]

    logger.info("🔧 Running FFmpeg render...")
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=1800,  # 30 minute timeout
        )

        if result.returncode != 0:
            logger.error(f"FFmpeg failed with exit code {result.returncode}")
            logger.error(f"FFmpeg stderr: {result.stderr[-2000:]}")
            return None

    except subprocess.TimeoutExpired:
        logger.error("FFmpeg render timed out after 30 minutes")
        return None
    except Exception as e:
        logger.error(f"FFmpeg crashed: {e}")
        return None

    # Verify output
    if not os.path.exists(output_path):
        logger.error("Output video file does not exist")
        return None

    file_size = os.path.getsize(output_path)
    if file_size < 1_000_000:  # Less than 1MB is suspicious
        logger.error(f"Output video too small ({file_size} bytes). Render may have failed.")
        return None

    logger.info(
        f"✅ Video assembled: {output_path} "
        f"({file_size / 1_000_000:.1f} MB, {audio_duration:.0f}s)"
    )

    # Cleanup concat file
    try:
        os.remove(concat_path)
    except Exception:
        pass

    return output_path
