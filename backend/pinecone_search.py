
import os
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pinecone import Pinecone

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is missing")

if not PINECONE_API_KEY or not PINECONE_INDEX_NAME:
    raise ValueError("Pinecone configuration is missing")

genai_client = genai.Client(api_key=GOOGLE_API_KEY)

pc = Pinecone(api_key=PINECONE_API_KEY)
index = pc.Index(PINECONE_INDEX_NAME)


def get_embedding(text):
    if not text or not text.strip():
        raise ValueError("Cannot create an embedding for empty text")

    result = genai_client.models.embed_content(
        model="gemini-embedding-001",
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_QUERY",
            output_dimensionality=768
        )
    )

    return result.embeddings[0].values


def normalize_text(text):
    if not text:
        return text

    return " ".join(word.capitalize() for word in text.split())


def query_pinecone(query_text, city_filter=None, cuisine_filter=None, top_k=3):
    query_embedding = get_embedding(query_text)

    filters = {}

    if city_filter:
        filters["city"] = {
            "$eq": normalize_text(city_filter)
        }

    if cuisine_filter:
        filters["cuisines"] = {
            "$in": [normalize_text(cuisine_filter)]
        }

    results = index.query(
        vector=query_embedding,
        top_k=top_k,
        filter=filters if filters else None,
        include_metadata=True
    )

    return results.matches
