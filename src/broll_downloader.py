"""
B-Roll Downloader — Downloads stock video clips from Pexels API based on visual keywords.
"""
import os
import time
import logging
import requests

from src.config import OUTPUT_DIR

logger = logging.getLogger(__name__)

PEXELS_BASE_URL = "https://api.pexels.com/videos/search"
MIN_CLIPS = 5


def _get_api_key():
    """Get Pexels API key from environment."""
    key = os.environ.get("PEXELS_API_KEY", "")
    if not key:
        raise ValueError("PEXELS_API_KEY environment variable is not set")
    return key


def _simplify_keyword(keyword):
    """Simplify a complex keyword for better Pexels results."""
    # Remove common adjectives and keep core nouns
    remove_words = {
        "indian", "detailed", "complex", "simple", "beautiful", "amazing",
        "professional", "corporate", "modern", "traditional", "specific",
    }
    words = keyword.lower().split()
    simplified = [w for w in words if w not in remove_words]
    # Take at most 3 words
    return " ".join(simplified[:3]) if simplified else keyword


def _search_and_download(keyword, api_key, output_path, max_retries=2):
    """Search Pexels for a keyword and download the best matching video."""
    headers = {"Authorization": api_key}

    for attempt in range(1, max_retries + 1):
        try:
            search_keyword = keyword if attempt == 1 else _simplify_keyword(keyword)

            params = {
                "query": search_keyword,
                "per_page": 3,
                "orientation": "landscape",
                "size": "medium",
            }

            response = requests.get(
                PEXELS_BASE_URL, headers=headers, params=params, timeout=30
            )

            # Handle rate limiting
            if response.status_code == 429:
                logger.warning("Pexels rate limited. Waiting 10s...")
                time.sleep(10)
                continue

            response.raise_for_status()
            data = response.json()
            videos = data.get("videos", [])

            if not videos:
                if attempt == 1:
                    logger.info(
                        f"No results for '{keyword}', trying simplified version..."
                    )
                    continue
                else:
                    logger.warning(f"No results for simplified '{search_keyword}' either")
                    return False

            # Find the best quality HD file
            best_file = None
            for video in videos:
                for vf in video.get("video_files", []):
                    if vf.get("quality") == "hd" and vf.get("width", 0) >= 1280:
                        best_file = vf
                        break
                if best_file:
                    break

            # Fallback: take any available file
            if not best_file:
                for video in videos:
                    files = video.get("video_files", [])
                    if files:
                        best_file = files[0]
                        break

            if not best_file:
                logger.warning(f"No downloadable files found for '{search_keyword}'")
                return False

            # Download the video file
            download_url = best_file.get("link", "")
            logger.info(f"📥 Downloading B-roll: '{search_keyword}' ({best_file.get('width')}x{best_file.get('height')})")

            dl_response = requests.get(download_url, timeout=120, stream=True)
            dl_response.raise_for_status()

            with open(output_path, "wb") as f:
                for chunk in dl_response.iter_content(chunk_size=8192):
                    f.write(chunk)

            file_size = os.path.getsize(output_path)
            if file_size < 10000:  # Less than 10KB is suspicious
                logger.warning(f"Downloaded file too small ({file_size} bytes)")
                os.remove(output_path)
                return False

            logger.info(f"✅ Saved: {output_path} ({file_size / 1024:.0f} KB)")
            return True

        except Exception as e:
            logger.warning(f"Download attempt {attempt} failed for '{keyword}': {e}")

    return False


def download(visual_keywords):
    """
    Download B-roll clips for a list of visual keywords.

    Args:
        visual_keywords: list of strings (e.g., ["stock market crash", "confused investor"])

    Returns:
        list of local file paths to downloaded clips, or empty list on failure
    """
    api_key = _get_api_key()
    broll_dir = os.path.join(OUTPUT_DIR, "broll")
    os.makedirs(broll_dir, exist_ok=True)

    downloaded = []

    logger.info(f"🎬 Downloading B-roll for {len(visual_keywords)} keywords...")

    for i, keyword in enumerate(visual_keywords):
        output_path = os.path.join(broll_dir, f"broll_{i:03d}.mp4")
        success = _search_and_download(keyword, api_key, output_path)

        if success:
            downloaded.append(output_path)

        # Small delay between API calls to avoid rate limiting
        time.sleep(1)

    logger.info(f"✅ Downloaded {len(downloaded)}/{len(visual_keywords)} B-roll clips")

    if len(downloaded) < MIN_CLIPS:
        logger.warning(
            f"Only {len(downloaded)} clips downloaded (minimum {MIN_CLIPS}). "
            f"Available clips will be looped."
        )

    return downloaded
