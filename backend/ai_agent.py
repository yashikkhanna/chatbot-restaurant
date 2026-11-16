
import os
import json
import time
from pathlib import Path
from datetime import date

from dotenv import load_dotenv
from google import genai
from google.genai import types


# Load the project root .env file
BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(ENV_PATH)

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in project root .env")

# Fast, lightweight model for intent extraction
MODEL_NAME = "gemini-3.5-flash-lite"

# Set a 20-second HTTP timeout
client = genai.Client(
    api_key=GOOGLE_API_KEY,
    http_options=types.HttpOptions(timeout=20000)
)


def get_today_date():
    return date.today().strftime("%Y-%m-%d")


def extract_intent_entities(user_input):

    if not user_input or not user_input.strip():
        raise ValueError("User input cannot be empty.")

    today = get_today_date()

    prompt = f"""
You are a restaurant chatbot intent and entity extraction system.

Today's date is {today}.

Extract information from the user's message.

Return exactly one JSON object with this structure:

{{
    "intent": "greeting",
    "entities": {{
        "city": null,
        "cuisine": null,
        "features": [],
        "date": null,
        "time": null,
        "number_of_people": null,
        "restaurant_name": null,
        "contact_name": null,
        "contact_email": null,
        "contact_number": null
    }}
}}

Allowed intents:
- greeting
- booking
- cancel
- other
- recommend

Rules:

1. Always include every entity field.
2. Use null for missing values.
3. Features must be a list.
4. Include only explicitly mentioned features.
5. Infer cuisine from dishes when reasonably clear.
6. Convert relative dates using today's date: {today}.
7. Return dates in YYYY-MM-DD format.
8. number_of_people must be an integer or null.
9. Do not invent contact information.
10. Return valid JSON only.

User message:
{json.dumps(user_input)}
"""

    start_time = time.perf_counter()

    try:
        response = client.models.generate_content(
            model=MODEL_NAME,
            contents=prompt,
            config=types.GenerateContentConfig(
                temperature=0,
                max_output_tokens=512,
                response_mime_type="application/json"
            )
        )

        elapsed = time.perf_counter() - start_time

        print(
            f"[Gemini] Model: {MODEL_NAME} | "
            f"Response time: {elapsed:.2f}s"
        )

        response_text = response.text

        if not response_text:
            raise RuntimeError("Gemini returned an empty response.")

        parsed = json.loads(response_text)

        if not isinstance(parsed, dict):
            raise ValueError("Gemini response is not a JSON object.")

        intent = parsed.get("intent")
        entities = parsed.get("entities")

        allowed_intents = {
            "greeting", "booking", "cancel", "other", "recommend"
        }

        if intent not in allowed_intents:
            intent = "other"

        if not isinstance(entities, dict):
            entities = {}

        required_fields = [
            "city",
            "cuisine",
            "features",
            "date",
            "time",
            "number_of_people",
            "restaurant_name",
            "contact_name",
            "contact_email",
            "contact_number"
        ]

        for field in required_fields:
            if field not in entities:
                entities[field] = [] if field == "features" else None

        if not isinstance(entities["features"], list):
            entities["features"] = []

        people = entities["number_of_people"]

        if people is not None:
            try:
                entities["number_of_people"] = int(people)
            except (ValueError, TypeError):
                entities["number_of_people"] = None

        parsed["intent"] = intent
        parsed["entities"] = entities

        return json.dumps(parsed, ensure_ascii=False)

    except Exception as e:
        elapsed = time.perf_counter() - start_time

        print(
            f"[Gemini ERROR] After {elapsed:.2f}s: "
            f"{type(e).__name__}: {e}"
        )

        raise RuntimeError(
            f"Gemini intent extraction failed: {type(e).__name__}"
        ) from e


if __name__ == "__main__":

    print("Restaurant chatbot Gemini test")
    print("Model:", MODEL_NAME)

    while True:

        user_input = input("\nYou: ").strip()

        if user_input.lower() in {"exit", "quit"}:
            break

        try:
            result = extract_intent_entities(user_input)

            print("\nGemini response:")
            print(json.dumps(json.loads(result), indent=4))

        except Exception as e:
            print("\nError:", e)
