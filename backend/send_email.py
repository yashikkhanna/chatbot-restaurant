
import os
import smtplib
import random
import ssl
from pathlib import Path

from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from fastapi import HTTPException
from dotenv import load_dotenv


# ========== Load Environment Variables ==========

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(ENV_PATH)


# ========== Gmail SMTP Configuration ==========

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465


# ========== Common Email Sending Function ==========

def send_email(message):

    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")

    if not email_user or not email_password:
        raise Exception(
            "EMAIL_USER or EMAIL_PASSWORD is missing in the .env file"
        )

    context = ssl.create_default_context()

    with smtplib.SMTP_SSL(
        SMTP_HOST,
        SMTP_PORT,
        context=context,
        timeout=30
    ) as server:

        server.login(email_user, email_password)
        server.send_message(message)


# ========== OTP Email ==========

def send_otp_email(to_email, otp, purpose):

    if purpose == "booking":

        subject = "🔐 OTP Verification for Table Booking"
        message_text = "Use the OTP below to confirm your booking:"
        bg_color = "#e3f2fd"
        heading_color = "#0d47a1"
        footer = (
            "This OTP is valid for 5 minutes. "
            "Please do not share it with anyone."
        )

    elif purpose == "cancellation":

        subject = "🔐 OTP Verification for Booking Cancellation"
        message_text = (
            "Use the OTP below to confirm your cancellation request:"
        )
        bg_color = "#fff3e0"
        heading_color = "#ef6c00"
        footer = (
            "This OTP is valid for 5 minutes. "
            "Only proceed if you're sure about cancelling."
        )

    else:

        raise HTTPException(
            status_code=400,
            detail="Invalid OTP purpose"
        )

    html_body = f"""
    <html>
    <body>

    <div style="font-family: Arial, sans-serif;
                padding: 20px;
                background-color: {bg_color};
                border-radius: 10px;">

        <h2 style="color: {heading_color};">
            OTP Verification
        </h2>

        <p>{message_text}</p>

        <div style="font-size: 26px;
                    font-weight: bold;
                    color: #000;
                    margin: 20px 0;">
            {otp}
        </div>

        <p style="font-size: 14px; color: #555;">
            {footer}
        </p>

    </div>

    </body>
    </html>
    """

    try:

        message = MIMEMultipart("alternative")

        message["Subject"] = subject
        message["From"] = os.getenv("EMAIL_USER")
        message["To"] = to_email

        message.attach(
            MIMEText(html_body, "html")
        )

        send_email(message)

        print(f"OTP email successfully sent to {to_email}")

    except Exception as e:

        print("Failed to send OTP email:", str(e))

        raise HTTPException(
            status_code=500,
            detail=f"Failed to send OTP: {str(e)}"
        )


# ========== Booking Confirmation Email ==========

def send_booking_confirmation_email(
    to_email,
    booking_id,
    name,
    contact_number,
    date,
    slot,
    restaurant_id,
    restaurant_name
):

    subject = "✅ Booking Confirmed – Your Table is Reserved!"

    html_body = f"""
    <html>
    <body>

    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                padding: 30px;
                background-color: #f3f4f6;
                border-radius: 10px;
                color: #333;">

        <h2 style="color: #1e88e5;">
            🎉 Booking Confirmation
        </h2>

        <p>Hi <strong>{name}</strong>,</p>

        <p>
            Your table booking has been
            <strong>successfully confirmed</strong>.
            Here are your reservation details:
        </p>

        <table style="width: 100%;
                      margin-top: 20px;
                      border-collapse: collapse;">

            <tr>
                <td style="padding: 8px;">
                    <strong>📌 Booking ID:</strong>
                </td>
                <td>{booking_id}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>🍽️ Restaurant:</strong>
                </td>
                <td>{restaurant_name} (ID: {restaurant_id})</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>📅 Date:</strong>
                </td>
                <td>{date}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>⏰ Time Slot:</strong>
                </td>
                <td>{slot}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>📞 Contact Number:</strong>
                </td>
                <td>{contact_number}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>📧 Email:</strong>
                </td>
                <td>{to_email}</td>
            </tr>

        </table>

        <p style="margin-top: 25px;">
            Thank you for choosing our service.
            We look forward to serving you! 😊
        </p>

        <hr style="margin: 30px 0;">

        <p style="font-size: 13px; color: #666;">
            Need to modify or cancel your booking?
            Just reply to this email or visit our website.
        </p>

    </div>

    </body>
    </html>
    """

    try:

        message = MIMEMultipart("alternative")

        message["Subject"] = subject
        message["From"] = os.getenv("EMAIL_USER")
        message["To"] = to_email

        message.attach(
            MIMEText(html_body, "html")
        )

        send_email(message)

        print(f"Booking confirmation email sent to {to_email}")

    except Exception as e:

        print("Failed to send confirmation email:", str(e))

        raise HTTPException(
            status_code=500,
            detail="Failed to send confirmation email."
        )


# ========== Cancellation Confirmation Email ==========

def send_cancellation_confirmation_email(
    to_email,
    booking_id,
    name,
    contact_number,
    date,
    slot,
    restaurant_id,
    restaurant_name
):

    subject = "❌ Booking Cancelled – Confirmation of Cancellation"

    html_body = f"""
    <html>
    <body>

    <div style="font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
                padding: 30px;
                background-color: #fdecea;
                border-radius: 10px;
                color: #333;">

        <h2 style="color: #e53935;">
            🚫 Booking Cancellation
        </h2>

        <p>Hi <strong>{name}</strong>,</p>

        <p>
            We confirm that your table booking has been
            <strong>successfully cancelled</strong>.
            Below are the details of the cancelled reservation:
        </p>

        <table style="width: 100%;
                      margin-top: 20px;
                      border-collapse: collapse;">

            <tr>
                <td style="padding: 8px;">
                    <strong>📌 Booking ID:</strong>
                </td>
                <td>{booking_id}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>🍽️ Restaurant:</strong>
                </td>
                <td>{restaurant_name} (ID: {restaurant_id})</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>📅 Date:</strong>
                </td>
                <td>{date}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>⏰ Time Slot:</strong>
                </td>
                <td>{slot}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>📞 Contact Number:</strong>
                </td>
                <td>{contact_number}</td>
            </tr>

            <tr>
                <td style="padding: 8px;">
                    <strong>📧 Email:</strong>
                </td>
                <td>{to_email}</td>
            </tr>

        </table>

        <p style="margin-top: 25px;">
            We hope to see you again soon.
            You're always welcome to book with us in the future!
        </p>

        <hr style="margin: 30px 0;">

        <p style="font-size: 13px; color: #666;">
            If this cancellation was not intended,
            please contact us immediately.
        </p>

    </div>

    </body>
    </html>
    """

    try:

        message = MIMEMultipart("alternative")

        message["Subject"] = subject
        message["From"] = os.getenv("EMAIL_USER")
        message["To"] = to_email

        message.attach(
            MIMEText(html_body, "html")
        )

        send_email(message)

        print(f"Cancellation confirmation email sent to {to_email}")

    except Exception as e:

        print("Failed to send cancellation email:", str(e))

        raise HTTPException(
            status_code=500,
            detail="Failed to send cancellation email."
        )


# ========== Manual Test Block ==========

if __name__ == "__main__":

    test_email = input("Enter email address to test: ")

    test_otp = str(random.randint(100000, 999999))

    test_purpose = input(
        "Enter purpose (booking/cancellation/confirm): "
    ).strip().lower()

    if test_purpose in ["booking", "cancellation"]:

        print("Sending OTP email...")

        send_otp_email(
            test_email,
            test_otp,
            test_purpose
        )

        print("OTP sent successfully!")

    elif test_purpose == "confirm":

        send_booking_confirmation_email(
            to_email=test_email,
            booking_id="BK123456",
            name="Test User",
            contact_number="0000000000",
            date="2025-07-01",
            slot="7:30 PM",
            restaurant_id=42,
            restaurant_name="Tandoori Flames"
        )

        print("Booking confirmation email sent!")

    else:

        print("Invalid purpose")
