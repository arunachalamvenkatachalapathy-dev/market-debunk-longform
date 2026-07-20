"""
Audio Generator — Uses Edge-TTS with dual voices to create podcast audio.
Stitches individual dialogue chunks with pydub.
"""
import os
import asyncio
import logging
import edge_tts
from pydub import AudioSegment

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

# Voice assignments
VOICES = {
    "english": {
        "A": "en-US-ChristopherNeural",  # Warm male voice
        "B": "en-US-AriaNeural",          # Expressive female voice
    },
    "tamil": {
        "A": "ta-IN-ValluvarNeural",      # Tamil male voice
        "B": "ta-IN-PallaviNeural",       # Tamil female voice
    },
}

SILENCE_BETWEEN_SPEAKERS_MS = 350  # 350ms pause between speakers
MIN_DURATION_SECONDS = 180         # 3 minutes minimum
MAX_DURATION_SECONDS = 1200        # 20 minutes maximum


async def _generate_chunk(text, voice, output_path):
    """Generate a single audio chunk using Edge-TTS."""
    communicate = edge_tts.Communicate(text, voice)
    await communicate.save(output_path)


def _generate_chunk_sync(text, voice, output_path, max_retries=3):
    """Synchronous wrapper for Edge-TTS generation with retries."""
    for attempt in range(1, max_retries + 1):
        try:
            asyncio.run(_generate_chunk(text, voice, output_path))
            # Verify the file was created and has content
            if os.path.exists(output_path) and os.path.getsize(output_path) > 100:
                return True
            else:
                logger.warning(f"Chunk file empty or missing (attempt {attempt})")
        except Exception as e:
            logger.warning(f"TTS chunk generation failed (attempt {attempt}): {e}")
    return False


def generate(script_data, language="english"):
    """
    Generate podcast audio from a script.

    Args:
        script_data: dict with "dialogue" array of {"speaker": "A"|"B", "text": str}
        language: "english" or "tamil"

    Returns:
        dict: {"path": str, "duration_seconds": float} or None on failure
    """
    dialogue = script_data.get("dialogue", [])
    if not dialogue:
        logger.error("No dialogue found in script data")
        return None

    voices = VOICES.get(language)
    if not voices:
        logger.error(f"Unsupported language: {language}")
        return None

    # Create temp directory for chunks
    chunks_dir = os.path.join(OUTPUT_DIR, f"audio_chunks_{language}")
    os.makedirs(chunks_dir, exist_ok=True)

    silence = AudioSegment.silent(duration=SILENCE_BETWEEN_SPEAKERS_MS)
    combined = AudioSegment.empty()
    successful_chunks = 0
    failed_chunks = 0

    logger.info(
        f"🎙️  Generating {language.upper()} audio: {len(dialogue)} dialogue lines"
    )

    for i, line in enumerate(dialogue):
        speaker = line.get("speaker", "A")
        text = line.get("text", "").strip()

        if not text:
            continue

        voice = voices.get(speaker, voices["A"])
        chunk_path = os.path.join(chunks_dir, f"chunk_{i:03d}.mp3")

        success = _generate_chunk_sync(text, voice, chunk_path)

        if success:
            try:
                chunk_audio = AudioSegment.from_mp3(chunk_path)
                combined += chunk_audio + silence
                successful_chunks += 1
            except Exception as e:
                logger.warning(f"Failed to load chunk {i}: {e}")
                failed_chunks += 1
        else:
            logger.warning(f"Skipping chunk {i} (speaker {speaker}) after retries")
            failed_chunks += 1

        # Progress logging every 10 chunks
        if (i + 1) % 10 == 0:
            logger.info(
                f"   Audio progress: {i + 1}/{len(dialogue)} chunks processed"
            )

    if successful_chunks == 0:
        logger.error("No audio chunks were successfully generated")
        return None

    duration_seconds = len(combined) / 1000.0
    logger.info(
        f"✅ Audio generated: {duration_seconds:.1f}s "
        f"({successful_chunks} chunks OK, {failed_chunks} failed)"
    )

    # Duration guard rails
    if duration_seconds < MIN_DURATION_SECONDS:
        logger.error(
            f"Audio too short ({duration_seconds:.0f}s < {MIN_DURATION_SECONDS}s). "
            f"Script may have been insufficient."
        )
        return None

    if duration_seconds > MAX_DURATION_SECONDS:
        logger.error(
            f"Audio too long ({duration_seconds:.0f}s > {MAX_DURATION_SECONDS}s). "
            f"Trimming to {MAX_DURATION_SECONDS}s."
        )
        combined = combined[: MAX_DURATION_SECONDS * 1000]
        duration_seconds = MAX_DURATION_SECONDS

    # Export final audio
    output_path = os.path.join(OUTPUT_DIR, f"podcast_{language}.mp3")
    combined.export(output_path, format="mp3", bitrate="192k")
    logger.info(f"💾 Audio saved to: {output_path}")

    # Cleanup chunks
    for f in os.listdir(chunks_dir):
        try:
            os.remove(os.path.join(chunks_dir, f))
        except Exception:
            pass
    try:
        os.rmdir(chunks_dir)
    except Exception:
        pass

    return {"path": output_path, "duration_seconds": duration_seconds}
