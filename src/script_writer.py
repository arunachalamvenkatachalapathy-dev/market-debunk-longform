"""
Script Writer — Uses Gemini to generate two-host podcast scripts in English and Tamil.
"""
import os
import json
import logging
from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

# Voice personas for the podcast
ENGLISH_SYSTEM_PROMPT = """You are a world-class podcast scriptwriter for a financial education show.

Write a natural, engaging, educational two-host podcast script.

HOST A (The Curious Investor): A relatable beginner who asks smart questions, expresses genuine surprise, 
and represents the average retail investor. They drive the conversation forward with follow-up questions.

HOST B (The Expert Analyst): An experienced, calm financial analyst who breaks down complex concepts 
into simple terms. They use real numbers, analogies, and practical takeaways.

RULES:
- Write 40 to 60 dialogue exchanges (aim for ~8-12 minutes when spoken)
- Make the conversation flow naturally — include reactions like "Wait, really?", "That's interesting!", "So you're saying..."
- Do NOT mention "CA Rachana Ranade" or any specific YouTuber by name
- Focus purely on the financial concepts, data, and lessons
- Start with an engaging hook that draws the listener in
- End with 2-3 actionable takeaways for the audience
- Include specific numbers, percentages, and data points from the source material
- Also generate 12-15 visual keywords that represent the key visual moments in the discussion"""

TAMIL_SYSTEM_PROMPT = """You are a world-class Tamil podcast scriptwriter for a financial education show.

Write the ENTIRE script in Tamil (தமிழ்). Every dialogue line must be in Tamil.

HOST A (ஆர்வமுள்ள முதலீட்டாளர்): A relatable beginner who asks smart questions in Tamil.

HOST B (நிபுணர் ஆய்வாளர்): An experienced financial analyst who explains concepts clearly in Tamil.

RULES:
- Write 40 to 60 dialogue exchanges in Tamil
- The Tamil should be natural spoken Tamil, NOT a literal translation from English
- Use Tamil financial terminology where appropriate (முதலீடு, பங்குச்சந்தை, லாபம் etc.)
- Do NOT mention any specific YouTuber by name
- Focus on financial concepts, data, and lessons
- Start with an engaging hook
- End with 2-3 actionable takeaways
- Include specific numbers and data points
- Also generate 12-15 visual keywords IN ENGLISH (since Pexels only supports English search)"""

SCRIPT_SCHEMA = types.Schema(
    type=types.Type.OBJECT,
    properties={
        "title": types.Schema(type=types.Type.STRING),
        "description": types.Schema(type=types.Type.STRING),
        "dialogue": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(
                type=types.Type.OBJECT,
                properties={
                    "speaker": types.Schema(type=types.Type.STRING),
                    "text": types.Schema(type=types.Type.STRING),
                },
                required=["speaker", "text"],
            ),
        ),
        "visual_keywords": types.Schema(
            type=types.Type.ARRAY,
            items=types.Schema(type=types.Type.STRING),
        ),
    },
    required=["title", "description", "dialogue", "visual_keywords"],
)


def _get_gemini_client():
    """Initialize Gemini client from environment."""
    api_keys_str = os.environ.get("LLM_API_KEYS", "")
    keys = [k.strip() for k in api_keys_str.split(",") if k.strip()]
    if not keys:
        raise ValueError("LLM_API_KEYS environment variable is not set")
    return genai.Client(api_key=keys[0])


def _call_gemini(client, system_prompt, user_prompt, max_retries=3):
    """Call Gemini with structured output and retry logic."""
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🤖 Calling Gemini (attempt {attempt}/{max_retries})...")
            response = client.models.generate_content(
                model="gemini-2.5-flash",
                contents=user_prompt,
                config=types.GenerateContentConfig(
                    system_instruction=system_prompt,
                    response_mime_type="application/json",
                    response_schema=SCRIPT_SCHEMA,
                    temperature=0.9,
                ),
            )

            result = json.loads(response.text)

            # Validate minimum dialogue count
            dialogue_count = len(result.get("dialogue", []))
            if dialogue_count < 20:
                logger.warning(
                    f"Script too short ({dialogue_count} exchanges). Retrying..."
                )
                continue

            logger.info(
                f"✅ Script generated: {dialogue_count} exchanges, "
                f"{len(result.get('visual_keywords', []))} visual keywords"
            )
            return result

        except Exception as e:
            logger.warning(f"Gemini call attempt {attempt} failed: {e}")

    logger.error("Failed to generate script after all retries")
    return None


def generate(topic_data, language="english"):
    """
    Generate a podcast script from topic data.

    Args:
        topic_data: dict with "title", "video_id", "transcript" (can be None)
        language: "english" or "tamil"

    Returns:
        dict with "title", "description", "dialogue", "visual_keywords"
        or None on failure
    """
    client = _get_gemini_client()
    title = topic_data["title"]
    transcript = topic_data.get("transcript")

    if language == "english":
        system_prompt = ENGLISH_SYSTEM_PROMPT
        if transcript:
            user_prompt = (
                f"Based on this transcript from a financial education video titled "
                f"'{title}', write a two-host podcast script.\n\n"
                f"TRANSCRIPT:\n{transcript}"
            )
        else:
            user_prompt = (
                f"Write a two-host podcast script about this financial topic: '{title}'. "
                f"Research and explain the key concepts that would be discussed in a "
                f"video with this title."
            )
    elif language == "tamil":
        system_prompt = TAMIL_SYSTEM_PROMPT
        if transcript:
            user_prompt = (
                f"Based on this transcript from a financial education video titled "
                f"'{title}', write a two-host podcast script ENTIRELY IN TAMIL (தமிழ்).\n\n"
                f"TRANSCRIPT:\n{transcript}"
            )
        else:
            user_prompt = (
                f"Write a two-host podcast script ENTIRELY IN TAMIL (தமிழ்) about this "
                f"financial topic: '{title}'."
            )
    else:
        raise ValueError(f"Unsupported language: {language}")

    logger.info(f"📝 Generating {language.upper()} podcast script for: {title}")
    script = _call_gemini(client, system_prompt, user_prompt)

    if script:
        logger.info(
            f"✅ {language.upper()} script ready: '{script.get('title', 'untitled')}'"
        )
    return script
