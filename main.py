"""
Market Debunk Longform — Full-length podcast video pipeline.

Orchestrates: Topic Scan → Script Generation → Audio → B-Roll → Video Assembly → Publish
"""
import os
import sys
import glob
import logging

# Ensure UTF-8 output
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

from src.config import OUTPUT_DIR
from src import topic_scanner, script_writer, audio_generator, broll_downloader, video_assembler, publisher

logger = logging.getLogger(__name__)


def cleanup_output():
    """Remove all pipeline-generated files from OUTPUT_DIR."""
    if not os.path.exists(OUTPUT_DIR):
        return
    patterns = [
        os.path.join(OUTPUT_DIR, "*.mp3"),
        os.path.join(OUTPUT_DIR, "*.mp4"),
        os.path.join(OUTPUT_DIR, "*.txt"),
    ]
    for pattern in patterns:
        for f in glob.glob(pattern):
            try:
                os.remove(f)
            except Exception:
                pass
    # Clean B-roll directory
    broll_dir = os.path.join(OUTPUT_DIR, "broll")
    if os.path.exists(broll_dir):
        for f in os.listdir(broll_dir):
            try:
                os.remove(os.path.join(broll_dir, f))
            except Exception:
                pass


def run_pipeline():
    """
    Main pipeline orchestrator.
    Returns True on success, False on failure.
    """
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    cleanup_output()

    # ═══════════════════════════════════════
    #  PHASE 1: TOPIC DISCOVERY
    # ═══════════════════════════════════════
    logger.info("=" * 60)
    logger.info("  PHASE 1: TOPIC DISCOVERY")
    logger.info("=" * 60)

    topic = topic_scanner.scan()
    if not topic:
        logger.error("🛑 No fresh topics found. Pipeline aborted.")
        return False

    logger.info(f"📌 Topic: {topic['title']}")
    logger.info(f"📝 Transcript available: {'Yes' if topic.get('transcript') else 'No (will extrapolate)'}")

    # ═══════════════════════════════════════
    #  PHASE 2: SCRIPT GENERATION
    # ═══════════════════════════════════════
    logger.info("=" * 60)
    logger.info("  PHASE 2: SCRIPT GENERATION (English + Tamil)")
    logger.info("=" * 60)

    en_script = script_writer.generate(topic, language="english")
    if not en_script:
        logger.error("🛑 English script generation failed. Pipeline aborted.")
        return False
    logger.info(f"📝 English script: {len(en_script['dialogue'])} exchanges")

    ta_script = script_writer.generate(topic, language="tamil")
    if not ta_script:
        logger.error("🛑 Tamil script generation failed. Pipeline aborted.")
        return False
    logger.info(f"📝 Tamil script: {len(ta_script['dialogue'])} exchanges")

    # ═══════════════════════════════════════
    #  PHASE 3: AUDIO GENERATION
    # ═══════════════════════════════════════
    logger.info("=" * 60)
    logger.info("  PHASE 3: AUDIO GENERATION (Dual Voice)")
    logger.info("=" * 60)

    en_audio = audio_generator.generate(en_script, language="english")
    if not en_audio:
        logger.error("🛑 English audio generation failed. Pipeline aborted.")
        return False
    logger.info(f"🎙️  English audio: {en_audio['duration_seconds']:.0f}s")

    ta_audio = audio_generator.generate(ta_script, language="tamil")
    if not ta_audio:
        logger.error("🛑 Tamil audio generation failed. Pipeline aborted.")
        return False
    logger.info(f"🎙️  Tamil audio: {ta_audio['duration_seconds']:.0f}s")

    # ═══════════════════════════════════════
    #  PHASE 4: B-ROLL DOWNLOAD
    # ═══════════════════════════════════════
    logger.info("=" * 60)
    logger.info("  PHASE 4: B-ROLL DOWNLOAD (Pexels)")
    logger.info("=" * 60)

    # Use English script's visual keywords (shared for both languages)
    visual_keywords = en_script.get("visual_keywords", [])
    if not visual_keywords:
        # Fallback generic keywords
        visual_keywords = [
            "stock market trading", "financial graph", "business meeting",
            "city skyline", "technology computer", "money finance",
            "investment portfolio", "economic growth", "bank building",
            "data analytics", "corporate office",
        ]

    broll_clips = broll_downloader.download(visual_keywords)
    if not broll_clips:
        logger.error("🛑 B-roll download failed. No clips available. Pipeline aborted.")
        return False
    logger.info(f"🎬 B-roll clips ready: {len(broll_clips)}")

    # ═══════════════════════════════════════
    #  PHASE 5: VIDEO ASSEMBLY
    # ═══════════════════════════════════════
    logger.info("=" * 60)
    logger.info("  PHASE 5: VIDEO ASSEMBLY (FFmpeg)")
    logger.info("=" * 60)

    en_video = video_assembler.assemble(en_audio, broll_clips, en_script, language="english")
    if not en_video:
        logger.error("🛑 English video assembly failed. Pipeline aborted.")
        return False
    logger.info(f"🎞️  English video: {en_video}")

    ta_video = video_assembler.assemble(ta_audio, broll_clips, ta_script, language="tamil")
    if not ta_video:
        logger.error("🛑 Tamil video assembly failed. Pipeline aborted.")
        return False
    logger.info(f"🎞️  Tamil video: {ta_video}")

    # ═══════════════════════════════════════
    #  PHASE 6: PUBLISH
    # ═══════════════════════════════════════
    logger.info("=" * 60)
    logger.info("  PHASE 6: PUBLISHING (YouTube + Telegram)")
    logger.info("=" * 60)

    en_result = publisher.upload_english(en_video, en_script)
    ta_result = publisher.upload_tamil(ta_video, ta_script)

    # Send Telegram notification with both links
    publisher.send_telegram_links(en_result, ta_result)

    # ═══════════════════════════════════════
    #  PHASE 7: PERSIST MEMORY
    # ═══════════════════════════════════════
    topic_scanner.mark_topic_used(topic["video_id"], topic["title"])

    # Final summary
    logger.info("=" * 60)
    en_status = "✅" if en_result.get("success") else "❌"
    ta_status = "✅" if ta_result.get("success") else "❌"
    logger.info(f"  PIPELINE COMPLETE")
    logger.info(f"  English YouTube: {en_status} {en_result.get('video_id', 'N/A')}")
    logger.info(f"  Tamil YouTube:   {ta_status} {ta_result.get('video_id', 'N/A')}")
    logger.info("=" * 60)

    return en_result.get("success", False) or ta_result.get("success", False)


if __name__ == "__main__":
    from dotenv import load_dotenv
    load_dotenv()

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        handlers=[logging.StreamHandler(sys.stdout)],
    )

    success = run_pipeline()
    sys.exit(0 if success else 1)
