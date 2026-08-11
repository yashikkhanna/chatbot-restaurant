import psycopg2
import json
import os
from dotenv import load_dotenv
from pathlib import Path


# Force load the correct .env inside backend/
env_path = Path(__file__).resolve().parent / ".env"
load_dotenv(dotenv_path=env_path)

print("🔍 DB_HOST =", os.getenv("DB_HOST"))

# Debug prints — check if env vars loaded correctly
print("DB_NAME:", os.getenv("DB_NAME"))
print("DB_USER:", os.getenv("DB_USER"))
print("DB_PASSWORD:", "******" if os.getenv("DB_PASSWORD") else None)
print("DB_HOST:", os.getenv("DB_HOST"))
print("DB_PORT:", os.getenv("DB_PORT"))

try:
    print("Connecting to the database...")
    conn = psycopg2.connect(
        dbname=os.getenv("DB_NAME"),
        user=os.getenv("DB_USER"),
        password=os.getenv("DB_PASSWORD"),
        host=os.getenv("DB_HOST"),
        port=os.getenv("DB_PORT", 5432)
    )
    cursor = conn.cursor()
    print("Connection successful!")

    # Create tables
    print("Creating tables if they do not exist...")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS restaurants (
        id SERIAL PRIMARY KEY,
        name TEXT NOT NULL,
        city TEXT NOT NULL,
        rating REAL,
        rating_count INTEGER,
        cost INTEGER,
        lic_no TEXT,
        address TEXT,
        capacity INTEGER,
        description TEXT,
        opening_time TEXT,
        closing_time TEXT
    );
    """)
    print("Table 'restaurants' ensured.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS cuisines (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    """)
    print("Table 'cuisines' ensured.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS restaurant_cuisines (
        restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
        cuisine_id INTEGER REFERENCES cuisines(id) ON DELETE CASCADE,
        PRIMARY KEY (restaurant_id, cuisine_id)
    );
    """)
    print("Table 'restaurant_cuisines' ensured.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS features (
        id SERIAL PRIMARY KEY,
        name TEXT UNIQUE NOT NULL
    );
    """)
    print("Table 'features' ensured.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS restaurant_features (
        restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
        feature_id INTEGER REFERENCES features(id) ON DELETE CASCADE,
        PRIMARY KEY (restaurant_id, feature_id)
    );
    """)
    print("Table 'restaurant_features' ensured.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS slots (
        id SERIAL PRIMARY KEY,
        restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
        time TEXT,
        is_booked BOOLEAN DEFAULT FALSE
    );
    """)
    print("Table 'slots' ensured.")

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS bookings (
        booking_id SERIAL PRIMARY KEY,
        restaurant_id INTEGER REFERENCES restaurants(id) ON DELETE CASCADE,
        user_name TEXT,
        contact_number TEXT,
        email TEXT,
        date DATE,
        slot TEXT
    );
    """)
    print("Table 'bookings' ensured.")
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS otps (
        id SERIAL PRIMARY KEY,
        email TEXT NOT NULL,
        otp TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)
    print("Table 'otps' ensured.")
    conn.commit()
    print("All tables created/verified successfully.")

    # Load data from JSON file
    print("Loading data from restaurants.json ...")
    with open('restaurants.json', 'r') as f:
        data = json.load(f)
    print(f"Loaded {len(data)} restaurants from JSON.")

    def get_or_create_id(table, name):
        print(f"Checking existence of '{name}' in table '{table}'...")
        cursor.execute(f"SELECT id FROM {table} WHERE name=%s;", (name,))
        row = cursor.fetchone()
        if row:
            print(f"Found existing id {row[0]} for '{name}'.")
            return row[0]
        print(f"'{name}' not found, inserting new record into '{table}'...")
        cursor.execute(f"INSERT INTO {table} (name) VALUES (%s) RETURNING id;", (name,))
        new_id = cursor.fetchone()[0]
        conn.commit()
        print(f"Inserted '{name}' with new id {new_id}.")
        return new_id

    for idx, restaurant in enumerate(data, start=1):
        print(f"Inserting/updating restaurant #{idx}: {restaurant.get('name')}")
        cursor.execute("""
            INSERT INTO restaurants (
                name, city, rating, rating_count, cost, lic_no,
                address, capacity, description, opening_time, closing_time
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (id) DO UPDATE SET
                name = EXCLUDED.name,
                city = EXCLUDED.city,
                rating = EXCLUDED.rating,
                rating_count = EXCLUDED.rating_count,
                cost = EXCLUDED.cost,
                lic_no = EXCLUDED.lic_no,
                address = EXCLUDED.address,
                capacity = EXCLUDED.capacity,
                description = EXCLUDED.description,
                opening_time = EXCLUDED.opening_time,
                closing_time = EXCLUDED.closing_time
            RETURNING id;
        """, (
            restaurant["name"],
            restaurant["city"],
            restaurant.get("rating"),
            restaurant.get("rating_count"),
            restaurant.get("cost"),
            restaurant.get("lic_no"),
            restaurant.get("address"),
            restaurant.get("capacity"),
            restaurant.get("description"),
            restaurant.get("opening_time"),
            restaurant.get("closing_time"),
        ))
        restaurant_id = cursor.fetchone()[0]
        print(f"Restaurant ID: {restaurant_id}")

        # Insert cuisines and link to restaurant
        for cuisine_name in restaurant.get("cuisine", []):
            cuisine_id = get_or_create_id("cuisines", cuisine_name)
            print(f"Linking cuisine '{cuisine_name}' (id {cuisine_id}) to restaurant id {restaurant_id}...")
            cursor.execute("""
                INSERT INTO restaurant_cuisines (restaurant_id, cuisine_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING;
            """, (restaurant_id, cuisine_id))

        # Insert features and link to restaurant
        for feature_name in restaurant.get("features", []):
            feature_id = get_or_create_id("features", feature_name)
            print(f"Linking feature '{feature_name}' (id {feature_id}) to restaurant id {restaurant_id}...")
            cursor.execute("""
                INSERT INTO restaurant_features (restaurant_id, feature_id)
                VALUES (%s, %s) ON CONFLICT DO NOTHING;
            """, (restaurant_id, feature_id))

        # Insert slots
        for slot in restaurant.get("daily_slots", []):
            print(f"Inserting slot '{slot}' for restaurant id {restaurant_id}...")
            cursor.execute("""
                INSERT INTO slots (restaurant_id, time, is_booked)
                VALUES (%s, %s, FALSE)
                ON CONFLICT DO NOTHING;
            """, (restaurant_id, slot))

    conn.commit()
    print("Data ingested successfully into PostgreSQL!")

except Exception as e:
    print("Error:", e)
finally:
    if 'cursor' in locals():
        cursor.close()
    if 'conn' in locals():
        conn.close()
    print("Database connection closed.")
