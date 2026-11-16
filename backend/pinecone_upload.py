
import os
import time
import re
import unicodedata
from pathlib import Path

import psycopg2
from dotenv import load_dotenv
from google import genai
from google.genai import types
from pinecone import Pinecone, ServerlessSpec


# ==========================================
# 1. LOAD ENVIRONMENT VARIABLES
# ==========================================

ROOT_DIR = Path(__file__).resolve().parent.parent
load_dotenv(ROOT_DIR / ".env")

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
PINECONE_API_KEY = os.getenv("PINECONE_API_KEY")
PINECONE_INDEX_NAME = os.getenv("PINECONE_INDEX_NAME")

if not GOOGLE_API_KEY:
    raise ValueError("GOOGLE_API_KEY is missing from .env")

if not PINECONE_API_KEY:
    raise ValueError("PINECONE_API_KEY is missing from .env")

if not PINECONE_INDEX_NAME:
    raise ValueError("PINECONE_INDEX_NAME is missing from .env")


# ==========================================
# 2. CONFIGURATION
# ==========================================

EMBEDDING_MODEL = "gemini-embedding-001"
EMBEDDING_DIMENSION = 768

BATCH_SIZE = 20

REQUEST_DELAY = 0.75

MAX_RETRIES = 5
RETRY_WAIT_SECONDS = 60

DELETE_MAX_ATTEMPTS = 30
DELETE_POLL_SECONDS = 2

UPLOAD_MAX_ATTEMPTS = 30
UPLOAD_POLL_SECONDS = 2


# ==========================================
# 3. INITIALIZE GEMINI
# ==========================================

client = genai.Client(api_key=GOOGLE_API_KEY)


# ==========================================
# 4. INITIALIZE PINECONE
# ==========================================

pc = Pinecone(api_key=PINECONE_API_KEY)

existing_indexes = pc.list_indexes().names()

if PINECONE_INDEX_NAME not in existing_indexes:

    print("\nPinecone index does not exist. Creating index...")

    pc.create_index(
        name=PINECONE_INDEX_NAME,
        dimension=EMBEDDING_DIMENSION,
        metric="cosine",
        spec=ServerlessSpec(
            cloud=os.getenv("PINECONE_CLOUD", "aws"),
            region=os.getenv("PINECONE_REGION", "us-west-2")
        )
    )

    print("Pinecone index created successfully.")

else:
    print("\nExisting Pinecone index found.")


index = pc.Index(PINECONE_INDEX_NAME)


# ==========================================
# 5. VERIFY PINECONE DIMENSION
# ==========================================

index_description = pc.describe_index(PINECONE_INDEX_NAME)

actual_dimension = index_description.dimension

if actual_dimension != EMBEDDING_DIMENSION:
    raise ValueError(
        f"Pinecone index dimension is {actual_dimension}, "
        f"but Gemini embedding dimension is {EMBEDDING_DIMENSION}. "
        "Stopping without deleting existing vectors."
    )

print("Pinecone dimension verified:", actual_dimension)


# ==========================================
# 6. GENERATE GEMINI EMBEDDINGS
# ==========================================

def get_embedding(text):

    if not text or not text.strip():
        raise ValueError("Cannot generate embedding for empty text.")

    result = client.models.embed_content(
        model=EMBEDDING_MODEL,
        contents=text,
        config=types.EmbedContentConfig(
            task_type="RETRIEVAL_DOCUMENT",
            output_dimensionality=EMBEDDING_DIMENSION
        )
    )

    return result.embeddings[0].values


# ==========================================
# 7. EMBEDDING WITH AUTOMATIC RETRIES
# ==========================================

def get_embedding_with_retry(text):

    for attempt in range(1, MAX_RETRIES + 1):

        try:

            embedding = get_embedding(text)

            time.sleep(REQUEST_DELAY)

            return embedding

        except Exception as e:

            error_message = str(e)

            if (
                "429" in error_message
                or "RESOURCE_EXHAUSTED" in error_message
            ):

                if attempt == MAX_RETRIES:
                    raise RuntimeError(
                        "Gemini quota exceeded after maximum retries."
                    ) from e

                wait_time = RETRY_WAIT_SECONDS * attempt

                print(
                    f"\nGemini rate limit reached. "
                    f"Retry {attempt}/{MAX_RETRIES}. "
                    f"Waiting {wait_time} seconds...\n"
                )

                time.sleep(wait_time)

            else:
                raise

    raise RuntimeError("Unable to generate embedding.")


# ==========================================
# 8. NORMALIZE RESTAURANT NAME AND CITY
# ==========================================

def normalize_text(value):

    if not value:
        return ""

    value = unicodedata.normalize("NFKC", str(value))
    value = value.casefold().strip()

    # Remove punctuation and normalize whitespace.
    value = "".join(
        char if char.isalnum() else " "
        for char in value
    )

    return " ".join(value.split())


def get_restaurant_key(name, city):

    return (
        normalize_text(name),
        normalize_text(city)
    )


# ==========================================
# 9. FETCH RESTAURANTS FROM POSTGRESQL
# ==========================================

print("\nConnecting to PostgreSQL...")

conn = psycopg2.connect(
    dbname=os.getenv("POSTGRES_DB", "sarvamAI_DB"),
    user=os.getenv("POSTGRES_USER", "postgres"),
    password=os.getenv("POSTGRES_PASSWORD"),
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432")
)

print("PostgreSQL connected successfully!")


try:

    with conn.cursor() as cursor:

        cursor.execute("""
            SELECT
                r.id,
                r.name,
                r.city,
                r.description,

                COALESCE(
                    array_agg(DISTINCT c.name)
                    FILTER (WHERE c.name IS NOT NULL),
                    ARRAY[]::text[]
                ) AS cuisines,

                COALESCE(
                    array_agg(DISTINCT f.name)
                    FILTER (WHERE f.name IS NOT NULL),
                    ARRAY[]::text[]
                ) AS features

            FROM restaurants r

            LEFT JOIN restaurant_cuisines rc
                ON r.id = rc.restaurant_id

            LEFT JOIN cuisines c
                ON rc.cuisine_id = c.id

            LEFT JOIN restaurant_features rf
                ON r.id = rf.restaurant_id

            LEFT JOIN features f
                ON rf.feature_id = f.id

            GROUP BY
                r.id,
                r.name,
                r.city,
                r.description

            ORDER BY r.id ASC;
        """)

        rows = cursor.fetchall()

    print("\n========================================")
    print("POSTGRESQL RESTAURANT SUMMARY")
    print("========================================")

    print("Total records fetched:", len(rows))


    # ==========================================
    # 10. REMOVE DUPLICATE RESTAURANTS
    # ==========================================

    unique_restaurants = []
    seen_restaurants = set()
    seen_ids = set()

    duplicate_count = 0
    skipped_count = 0

    print("\nChecking for duplicate restaurants...")

    for row in rows:

        (
            restaurant_id,
            name,
            city,
            description,
            cuisines,
            features
        ) = row

        # Avoid duplicate Pinecone vector IDs.
        if restaurant_id in seen_ids:

            print(
                f"Duplicate restaurant ID skipped: {restaurant_id}"
            )

            duplicate_count += 1
            continue

        seen_ids.add(restaurant_id)

        # A valid name and city are required for deduplication.
        if not normalize_text(name) or not normalize_text(city):

            print(
                f"Skipping ID {restaurant_id}: "
                "restaurant name or city is missing."
            )

            skipped_count += 1
            continue

        # Name + city is the duplicate detection key.
        restaurant_key = get_restaurant_key(name, city)

        if restaurant_key in seen_restaurants:

            print(
                f"DUPLICATE SKIPPED: {name} - {city} "
                f"(ID: {restaurant_id})"
            )

            duplicate_count += 1
            continue

        seen_restaurants.add(restaurant_key)

        if not description or not str(description).strip():

            print(
                f"Skipping {name} (ID: {restaurant_id}): "
                "description is missing."
            )

            skipped_count += 1
            continue

        unique_restaurants.append(row)

    print("\n========================================")
    print("DUPLICATE CHECK RESULT")
    print("========================================")

    print("Original PostgreSQL records:", len(rows))
    print("Duplicate records removed:", duplicate_count)
    print("Records skipped:", skipped_count)
    print("Unique restaurants to process:", len(unique_restaurants))


    # ==========================================
    # 11. GENERATE ALL EMBEDDINGS FIRST
    # ==========================================

    print("\n========================================")
    print("GENERATING RESTAURANT EMBEDDINGS")
    print("========================================")

    vectors = []

    for position, row in enumerate(
        unique_restaurants,
        start=1
    ):

        (
            restaurant_id,
            name,
            city,
            description,
            cuisines,
            features
        ) = row

        cuisines = [
            item for item in (cuisines or []) if item
        ]

        features = [
            item for item in (features or []) if item
        ]

        combined_text = (
            f"Restaurant: {name}\n"
            f"City: {city}\n"
            f"Description: {description}\n"
            f"Cuisines: {', '.join(cuisines)}\n"
            f"Features: {', '.join(features)}"
        )

        metadata = {
            "restaurant_id": str(restaurant_id),
            "name": name,
            "city": city,
            "cuisines": cuisines,
            "features": features
        }

        print(
            f"\nGenerating embedding "
            f"{position}/{len(unique_restaurants)}: "
            f"{name} (ID: {restaurant_id})"
        )

        embedding = get_embedding_with_retry(combined_text)

        vectors.append(
            (
                str(restaurant_id),
                embedding,
                metadata
            )
        )

    # Final local duplicate-ID safety check.
    vector_ids = [vector[0] for vector in vectors]

    if len(vector_ids) != len(set(vector_ids)):
        raise RuntimeError(
            "Duplicate vector IDs detected before upload. "
            "Stopping to protect Pinecone."
        )

    print("\nAll embeddings generated successfully.")
    print("Unique vectors prepared:", len(vectors))


    # ==========================================
    # 12. EMPTY PINECONE INDEX
    # ==========================================

    print("\n========================================")
    print("CLEARING EXISTING PINECONE VECTORS")
    print("========================================")

    stats_before = index.describe_index_stats()

    vectors_before = stats_before.total_vector_count or 0

    print("Existing vectors before deletion:", vectors_before)

    if vectors_before > 0:

        print("\nSending delete-all request to Pinecone...")

        # No namespace specified:
        # deletes vectors across all namespaces.
        index.delete(delete_all=True)

        print("Delete request submitted successfully.")

        deletion_verified = False

        for attempt in range(1, DELETE_MAX_ATTEMPTS + 1):

            time.sleep(DELETE_POLL_SECONDS)

            updated_stats = index.describe_index_stats()

            remaining = updated_stats.total_vector_count or 0

            print(
                f"Deletion verification "
                f"{attempt}/{DELETE_MAX_ATTEMPTS}: "
                f"{remaining} vectors remaining"
            )

            if remaining == 0:

                deletion_verified = True
                break

        if not deletion_verified:

            raise RuntimeError(
                "Pinecone deletion could not be verified. "
                "Upload cancelled to avoid mixing old and new vectors."
            )

        print("\nPINECONE DELETION VERIFIED.")

    else:

        print("Pinecone index was already empty.")

    deleted_count = vectors_before

    print("\n========================================")
    print("PINECONE DELETION SUMMARY")
    print("========================================")

    print("Vectors present before deletion:", vectors_before)
    print("Vectors deleted:", deleted_count)
    print("Vectors remaining:", 0)


    # ==========================================
    # 13. UPLOAD UNIQUE VECTORS IN BATCHES
    # ==========================================

    print("\n========================================")
    print("UPLOADING NEW RESTAURANT VECTORS")
    print("========================================")

    total_uploaded = 0

    for start in range(0, len(vectors), BATCH_SIZE):

        batch = vectors[start:start + BATCH_SIZE]

        response = index.upsert(vectors=batch)

        batch_uploaded = getattr(
            response,
            "upserted_count",
            len(batch)
        )

        total_uploaded += batch_uploaded

        print(
            f"Batch {start // BATCH_SIZE + 1}: "
            f"{batch_uploaded} vectors uploaded. "
            f"Total uploaded: {total_uploaded}"
        )


    # ==========================================
    # 14. VERIFY FINAL PINECONE COUNT
    # ==========================================

    print("\n========================================")
    print("VERIFYING FINAL PINECONE DATA")
    print("========================================")

    expected_count = len(vectors)

    final_count = None

    for attempt in range(1, UPLOAD_MAX_ATTEMPTS + 1):

        time.sleep(UPLOAD_POLL_SECONDS)

        final_stats = index.describe_index_stats()

        final_count = final_stats.total_vector_count or 0

        print(
            f"Upload verification "
            f"{attempt}/{UPLOAD_MAX_ATTEMPTS}: "
            f"{final_count}/{expected_count} vectors visible"
        )

        if final_count == expected_count:
            break

    if final_count != expected_count:

        raise RuntimeError(
            f"Final Pinecone count mismatch. "
            f"Expected {expected_count}, found {final_count}."
        )


    # ==========================================
    # 15. FINAL REPORT
    # ==========================================

    print("\n")
    print("=" * 50)
    print("RESTAURANT EMBEDDING UPLOAD COMPLETE")
    print("=" * 50)

    print("PostgreSQL records fetched:", len(rows))
    print("Duplicate restaurants skipped:", duplicate_count)
    print("Other records skipped:", skipped_count)
    print("Unique restaurants processed:", len(vectors))

    print("\nPINECONE SUMMARY")

    print("Vectors before deletion:", vectors_before)
    print("Vectors deleted:", deleted_count)
    print("New vectors uploaded:", total_uploaded)
    print("Final Pinecone vector count:", final_count)

    print("\nPinecone index:", PINECONE_INDEX_NAME)

    print("\nFinal Pinecone statistics:")
    print(final_stats)

    print("\nSUCCESS: Pinecone contains the newly uploaded unique restaurants.")

finally:

    conn.close()

    print("\nPostgreSQL connection closed.")
