from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from pydantic import BaseModel, Field, EmailStr
from typing import Optional, List
from datetime import date
import json
import re
import random

from db_querries import (
    make_booking, cancel_booking_by_id, check_availability,
    search_bookings_by_user, save_otp, validate_otp,get_restaurant_name_by_id,get_booking_by_id
)
from ai_agent import extract_intent_entities
from pinecone_search import query_pinecone
from send_email import send_otp_email,send_booking_confirmation_email,send_cancellation_confirmation_email

app = FastAPI()

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ========== In-memory cache for OTP verification ==========
verified_otp_cache = {}

# ========== Utility ==========

def parse_entities(json_str: str):
    if not json_str or json_str.strip() == "":
        return {}
    cleaned = re.sub(r"^```json\s*|```$", "", json_str.strip(), flags=re.DOTALL)
    try:
        return json.loads(cleaned)
    except Exception as e:
        print("Failed to parse extracted intent/entities JSON:", e)
        return {}

# ========== Pydantic Models ==========

class IntentRequest(BaseModel):
    user_input: str

class IntentResponse(BaseModel):
    intent: Optional[str]
    entities: Optional[dict]

class RecommendationRequest(BaseModel):
    user_query: str
    city: Optional[str] = None
    cuisine: Optional[str] = None

class RecommendationItem(BaseModel):
    id: str
    name: Optional[str]
    city: Optional[str]
    cuisines: List[str] = []
    features: List[str] = []

class RecommendationResponse(BaseModel):
    recommendations: List[RecommendationItem]

class AvailabilityRequest(BaseModel):
    restaurant_id: int
    date: date

class AvailabilityResponse(BaseModel):
    available_slots: List[str]

class BookingRequest(BaseModel):
    restaurant_id: int
    contact_name: str
    contact_number: str
    contact_email: EmailStr
    date: date
    slot: str
    number_of_people: Optional[int] = Field(1, gt=0)

class BookingResponse(BaseModel):
    success: bool
    message: str
    booking_id: Optional[str] = None

class CancelRequest(BaseModel):
    booking_id: str
    contact_email: EmailStr 

class CancelResponse(BaseModel):
    success: bool
    message: str

class GetBookingsRequest(BaseModel):
    contact_number: str
    contact_email: EmailStr

class BookingItem(BaseModel):
    booking_id: str
    restaurant_id: int
    name: str
    date: date
    time_slot: str

class GetBookingsResponse(BaseModel):
    bookings: List[BookingItem]

class SendOTPRequest(BaseModel):
    email: EmailStr
    purpose: str  # booking / cancellation

class ValidateOTPRequest(BaseModel):
    email: EmailStr
    otp: str
    purpose: str  # booking / cancellation

# ========== Error Handler ==========

@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    print("❌ Validation error details:", exc.errors())
    body = await request.body()
    print("➡️ Request body causing error:", body.decode())
    return JSONResponse(status_code=422, content={"detail": exc.errors()})

# ========== Routes ==========


@app.post("/intent", response_model=IntentResponse)
def get_intent(data: IntentRequest):

    try:
        raw_output = extract_intent_entities(data.user_input)
        parsed = parse_entities(raw_output)

        if not parsed:
            raise HTTPException(
                status_code=502,
                detail="Could not extract intent from Gemini response."
            )

        return IntentResponse(
            intent=parsed.get("intent", "other"),
            entities=parsed.get("entities", {})
        )

    except HTTPException:
        raise

    except Exception as e:
        print("[INTENT ERROR]", repr(e))

        raise HTTPException(
            status_code=502,
            detail="Gemini intent extraction failed. Please try again."
        )


@app.post("/recommendations", response_model=RecommendationResponse)
def get_recommendations(data: RecommendationRequest):
    results = query_pinecone(
        data.user_query,
        city_filter=data.city,
        cuisine_filter=data.cuisine,
        top_k=3
    )

    recs = []

    for res in results or []:
        meta = res.metadata or {}

        recs.append(
            RecommendationItem(
                id=res.id,
                name=meta.get("name"),
                city=meta.get("city"),
                cuisines=meta.get("cuisines", []),
                features=meta.get("features", [])
            )
        )

    return {"recommendations": recs}

@app.post("/availability", response_model=AvailabilityResponse)
def get_availability(data: AvailabilityRequest):
    slots = check_availability(data.restaurant_id, data.date)
    return {"available_slots": slots}

@app.post("/book", response_model=BookingResponse)
def book(data: BookingRequest):
    # ✅ Enforce OTP verification
    if not verified_otp_cache.get((data.contact_email, "booking")):
        raise HTTPException(status_code=401, detail="OTP not verified for booking")

    try:
        booking_id = make_booking(
            restaurant_id=data.restaurant_id,
            user_name=data.contact_name,
            contact_number=data.contact_number,
            email=data.contact_email,
            date=data.date,
            slot=data.slot
        )
        if booking_id:
            # ✅ Clear OTP flag after booking
            verified_otp_cache.pop((data.contact_email, "booking"), None)

            # ✅ Fetch restaurant name from DB
            restaurant_name = get_restaurant_name_by_id(data.restaurant_id)

            # ✅ Send confirmation email
            send_booking_confirmation_email(
                to_email=data.contact_email,
                booking_id=str(booking_id),
                name=data.contact_name,
                contact_number=data.contact_number,
                date=str(data.date),
                slot=data.slot,
                restaurant_id=data.restaurant_id,
                restaurant_name=restaurant_name
            )

            return BookingResponse(success=True, message="Booking confirmed!", booking_id=str(booking_id))
        else:
            return BookingResponse(success=False, message="Booking failed: Slot already booked")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/cancel", response_model=CancelResponse)
def cancel(data: CancelRequest):
    if not verified_otp_cache.get((data.contact_email, "cancellation")):
        raise HTTPException(status_code=401, detail="OTP not verified for cancellation")

    try:
        # ✅ Fetch booking details from DB
        booking = get_booking_by_id(data.booking_id)
        if not booking:
            raise HTTPException(status_code=404, detail="Booking not found")

        # ✅ Double-check email matches
        if booking["email"] != data.contact_email:
            raise HTTPException(status_code=403, detail="Email does not match booking")

        # ✅ Cancel booking
        success = cancel_booking_by_id(data.booking_id)
        if success:
            verified_otp_cache.pop((data.contact_email, "cancellation"), None)

            # ✅ Send cancellation confirmation email
            send_cancellation_confirmation_email(
                to_email=booking["email"],
                booking_id=booking["booking_id"],
                name=booking["user_name"],
                contact_number=booking["contact_number"],
                date=str(booking["date"]),
                slot=booking["slot"],
                restaurant_id=booking["restaurant_id"],
                restaurant_name=booking["restaurant_name"]
            )

            return CancelResponse(success=True, message="Booking cancelled successfully")
        else:
            raise HTTPException(status_code=404, detail="Booking ID not found")

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



@app.post("/bookings", response_model=GetBookingsResponse)
def get_bookings(data: GetBookingsRequest):
    bookings = search_bookings_by_user(data.contact_number, data.contact_email)
    result = []
    for b in bookings:
        result.append(BookingItem(
            booking_id=str(b[0]),
            restaurant_id=b[1],
            name=b[2],
            date=b[3],
            time_slot=b[4]
        ))
    return {"bookings": result}

@app.post("/send-otp")
def send_otp(data: SendOTPRequest):
    if data.purpose not in ["booking", "cancellation"]:
        raise HTTPException(status_code=400, detail="Purpose must be 'booking' or 'cancellation'")
    otp = str(random.randint(100000, 999999))
    save_otp(data.email, otp)
    try:
        send_otp_email(to_email=data.email, otp=otp, purpose=data.purpose)
        return {"success": True, "message": f"OTP sent to {data.email} for {data.purpose} verification"}
    except HTTPException as e:
        raise e

@app.post("/validate-otp")
def validate_otp_route(data: ValidateOTPRequest):
    if data.purpose not in ["booking", "cancellation"]:
        raise HTTPException(status_code=400, detail="Purpose must be 'booking' or 'cancellation'")
    if validate_otp(data.email, data.otp):
        verified_otp_cache[(data.email, data.purpose)] = True  # ✅ Mark OTP as verified
        return {"success": True, "message": "OTP validated"}
    else:
        raise HTTPException(status_code=401, detail="Invalid or expired OTP")




# To run this API: uvicorn app:app --reload
