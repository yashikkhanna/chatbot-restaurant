from fastapi.testclient import TestClient 
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app


client = TestClient(app)

def test_intent_route():
    response = client.post("/intent", json={"user_input": "Book a table for 2 in Delhi for Chinese cuisine"})
    assert response.status_code == 200
    data = response.json()
    assert "intent" in data
    assert "entities" in data

def test_recommendations_route():
    response = client.post("/recommendations", json={
        "user_query": "Chinese restaurants in Delhi",
        "city": "Delhi",
        "cuisine": "Chinese"
    })
    assert response.status_code == 200
    assert "recommendations" in response.json()

def test_availability_route():
    response = client.post("/availability", json={
        "restaurant_id": 1,
        "date": "2025-07-10"
    })
    assert response.status_code == 200
    assert "available_slots" in response.json()

def test_bookings_route_empty():
    response = client.post("/bookings", json={
        "contact_email": "testuser@example.com",
        "contact_number": "9999999999"
    })
    assert response.status_code == 200
    assert "bookings" in response.json()

def test_send_otp_route():
    response = client.post("/send-otp", json={
        "email": "testuser@example.com",
        "purpose": "booking"
    })
    assert response.status_code == 200
    data = response.json()
    assert data.get("success") is True

def test_validate_otp_route_invalid():
    response = client.post("/validate-otp", json={
        "email": "testuser@example.com",
        "otp": "000000",  # dummy OTP; expected to fail
        "purpose": "booking"
    })
    assert response.status_code == 401  # Invalid OTP

# Add the following only if you're mocking DB/OTP properly
# def test_booking_route_without_otp():
#     response = client.post("/book", json={
#         "restaurant_id": 1,
#         "contact_name": "Test User",
#         "contact_email": "testuser@example.com",
#         "contact_number": "9999999999",
#         "date": "2025-07-10",
#         "slot": "12:00 PM",
#         "number_of_people": 2
#     })
#     assert response.status_code == 401  # OTP not verified
