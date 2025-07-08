import psycopg2
from datetime import datetime, timedelta
from dotenv import load_dotenv
import os

# Load environment variables from .env file
load_dotenv()

# Database connection setup using env vars
conn = psycopg2.connect(
    dbname=os.getenv("DB_NAME"),
    user=os.getenv("DB_USER"),
    password=os.getenv("DB_PASSWORD"),
    host=os.getenv("DB_HOST"),
    port=os.getenv("DB_PORT", 5432)
)
cursor = conn.cursor()

# ========== BOOKING FUNCTIONS ==========

def make_booking(restaurant_id, user_name, contact_number, email, date, slot):
    try:
        cursor.execute("""
            SELECT 1 FROM bookings
            WHERE restaurant_id = %s AND date = %s AND slot = %s;
        """, (restaurant_id, date, slot))

        if cursor.fetchone():
            return None  # Slot already booked

        cursor.execute("""
            INSERT INTO bookings (
                restaurant_id, user_name, contact_number, email, date, slot
            ) VALUES (%s, %s, %s, %s, %s, %s)
            RETURNING booking_id;
        """, (restaurant_id, user_name, contact_number, email, date, slot))

        booking_id = cursor.fetchone()[0]
        conn.commit()
        return booking_id

    except Exception as e:
        print("❌ Error in make_booking:", e)
        conn.rollback()
        return None

def cancel_booking_by_id(booking_id):
    try:
        cursor.execute("""
            DELETE FROM bookings
            WHERE booking_id = %s;
        """, (booking_id,))
        deleted = cursor.rowcount
        conn.commit()
        return deleted > 0

    except Exception as e:
        print("❌ Error in cancel_booking_by_id:", e)
        conn.rollback()
        return False

def search_bookings_by_user(contact_number, email):
    try:
        cursor.execute("""
            SELECT b.booking_id, b.restaurant_id, r.name, b.date, b.slot
            FROM bookings b
            JOIN restaurants r ON b.restaurant_id = r.id
            WHERE b.contact_number = %s AND b.email = %s;
        """, (contact_number, email))

        return cursor.fetchall()

    except Exception as e:
        print("❌ Error in search_bookings_by_user:", e)
        conn.rollback()
        return []

def check_availability(restaurant_id, date):
    try:
        cursor.execute("SELECT time FROM slots WHERE restaurant_id = %s;", (restaurant_id,))
        all_slots = [row[0] for row in cursor.fetchall()]

        cursor.execute("""
            SELECT slot FROM bookings
            WHERE restaurant_id = %s AND date = %s;
        """, (restaurant_id, date))
        booked_slots = [row[0] for row in cursor.fetchall()]

        available_slots = list(set(all_slots) - set(booked_slots))
        return sorted(available_slots)

    except Exception as e:
        print("❌ Error in check_availability:", e)
        conn.rollback()
        return []

# ========== OTP FUNCTIONS ==========

def save_otp(email, otp):
    try:
        cursor.execute("""
            INSERT INTO otps (email, otp, created_at)
            VALUES (%s, %s, CURRENT_TIMESTAMP);
        """, (email, otp))
        conn.commit()

    except Exception as e:
        print("❌ Error in save_otp:", e)
        conn.rollback()

def validate_otp(email, otp):
    try:
        cursor.execute("""
            SELECT created_at FROM otps
            WHERE email = %s AND otp = %s
            ORDER BY created_at DESC LIMIT 1;
        """, (email, otp))

        result = cursor.fetchone()
        if not result:
            return False

        created_at = result[0]
        if datetime.utcnow() - created_at > timedelta(minutes=5):
            return False

        return True

    except Exception as e:
        print("❌ Error in validate_otp:", e)
        conn.rollback()
        return False

# ========== MISC FUNCTIONS ==========

def get_restaurant_name_by_id(restaurant_id):
    try:
        cursor.execute("""
            SELECT name FROM restaurants
            WHERE id = %s;
        """, (restaurant_id,))
        result = cursor.fetchone()
        return result[0] if result else "Unknown Restaurant"

    except Exception as e:
        print("❌ Error in get_restaurant_name_by_id:", e)
        conn.rollback()
        return "Unknown Restaurant"

def get_booking_by_id(booking_id):
    try:
        cursor.execute("""
            SELECT b.booking_id, b.user_name, b.contact_number, b.email, b.date, b.slot, b.restaurant_id, r.name
            FROM bookings b
            JOIN restaurants r ON b.restaurant_id = r.id
            WHERE b.booking_id = %s;
        """, (booking_id,))
        
        result = cursor.fetchone()
        if result:
            return {
                "booking_id": result[0],
                "user_name": result[1],
                "contact_number": result[2],
                "email": result[3],
                "date": result[4],
                "slot": result[5],
                "restaurant_id": result[6],
                "restaurant_name": result[7],
            }
        else:
            return None

    except Exception as e:
        print("❌ Error in get_booking_by_id:", e)
        conn.rollback()
        return None

# ========== CONNECTION CLEANUP ==========

def close_connection():
    cursor.close()
    conn.close()
