"""
Topic Scanner — Fetches the latest long-form video from CA Rachana Ranade's channel.
Skips Shorts, checks against used_topics.json, extracts transcript.
"""
import os
import json
import logging
import time
import requests
import xml.etree.ElementTree as ET

from src.config import RSS_URL, MAX_TRANSCRIPT_CHARS

logger = logging.getLogger(__name__)

USED_TOPICS_FILE = "used_topics.json"


def _load_used_topics():
    """Load the list of previously used video IDs."""
    if os.path.exists(USED_TOPICS_FILE):
        with open(USED_TOPICS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _is_topic_used(video_id):
    """Check if a video ID has already been processed."""
    used = _load_used_topics()
    return any(entry.get("video_id") == video_id for entry in used)


def _fetch_rss(max_retries=3):
    """Fetch RSS feed with retry and backoff."""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"📡 Fetching RSS feed (attempt {attempt}/{max_retries})...")
            response = requests.get(RSS_URL, timeout=30)
            response.raise_for_status()
            return response.text
        except Exception as e:
            logger.warning(f"RSS fetch attempt {attempt} failed: {e}")
            if attempt < max_retries:
                time.sleep(5 * attempt)  # Exponential backoff
    return None


def _extract_transcript(video_id):
    """Extract transcript from a YouTube video using youtube-transcript-api."""
    try:
        from youtube_transcript_api import YouTubeTranscriptApi
        logger.info(f"📝 Extracting transcript for video: {video_id}")
        transcript_obj = YouTubeTranscriptApi().fetch(video_id)
        full_text = " ".join([snippet.text for snippet in transcript_obj.snippets])

        # Safety cap
        if len(full_text) > MAX_TRANSCRIPT_CHARS:
            full_text = full_text[:MAX_TRANSCRIPT_CHARS]
            logger.info(f"Transcript truncated to {MAX_TRANSCRIPT_CHARS} chars")

        word_count = len(full_text.split())
        logger.info(f"Transcript extracted: {word_count} words")
        return full_text

    except Exception as e:
        logger.warning(f"Could not fetch transcript for {video_id}: {e}")
        return None


def scan():
    """
    Main scanner function.
    Returns dict: {"title": str, "video_id": str, "transcript": str or None}
    Returns None if no fresh topic is found.
    """
    rss_xml = _fetch_rss()
    if not rss_xml:
        logger.error("Failed to fetch RSS feed after all retries. Aborting.")
        return None

    try:
        root = ET.fromstring(rss_xml)
        ns = {
            "a": "http://www.w3.org/2005/Atom",
            "yt": "http://www.youtube.com/xml/schemas/2015",
        }

        for entry in root.findall("a:entry", ns):
            title = entry.find("a:title", ns).text
            video_id = entry.find("yt:videoId", ns).text
            link_elem = entry.find("a:link", ns)
            link_href = link_elem.attrib.get("href", "") if link_elem is not None else ""

            # Skip YouTube Shorts
            if "/shorts/" in link_href:
                logger.info(f"⏭️  Skipping Short: {title}")
                continue

            # Skip already processed videos
            if _is_topic_used(video_id):
                logger.info(f"⏭️  Already used: {title}")
                continue

            # Found a fresh long-form video
            logger.info(f"✅ Fresh long-form video found: {title}")
            transcript = _extract_transcript(video_id)

            if transcript and len(transcript.split()) < 100:
                logger.warning("Transcript too short (<100 words), treating as unavailable")
                transcript = None

            return {
                "title": title,
                "video_id": video_id,
                "transcript": transcript,
            }

        logger.warning("No fresh long-form videos found in RSS feed.")
        return None

    except ET.ParseError as e:
        logger.error(f"Failed to parse RSS XML: {e}")
        return None


def mark_topic_used(video_id, title):
    """Record a video as processed in used_topics.json."""
    used = _load_used_topics()
    used.append({"video_id": video_id, "title": title})
    with open(USED_TOPICS_FILE, "w", encoding="utf-8") as f:
        json.dump(used, f, indent=2, ensure_ascii=False)
    logger.info(f"📝 Marked topic as used: {title}")
