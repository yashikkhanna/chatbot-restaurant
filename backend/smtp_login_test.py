
import os
import ssl
import smtplib
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR.parent / ".env")

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

if not EMAIL_USER or not EMAIL_PASSWORD:
    raise SystemExit("Email credentials are missing.")

server = None

try:
    print("Connecting to Gmail...")

    server = smtplib.SMTP_SSL(
        "smtp.gmail.com",
        465,
        context=ssl.create_default_context(),
        timeout=30
    )

    print("SSL connection successful.")

    server.ehlo()

    print("Testing LOGIN authentication...")

    def login_auth(challenge=None):
        if challenge is None:
            return None

        prompt = challenge.decode(errors="ignore").lower()

        if "username" in prompt:
            return EMAIL_USER

        if "password" in prompt:
            return EMAIL_PASSWORD

        return ""

    result = server.auth(
        "LOGIN",
        login_auth,
        initial_response_ok=False
    )

    print("AUTHENTICATION SUCCESSFUL:", result[0])

    recipient = input("Enter recipient email: ").strip()

    from email.mime.text import MIMEText

    message = MIMEText("Gmail SMTP authentication test successful.")
    message["Subject"] = "SMTP Login Test"
    message["From"] = EMAIL_USER
    message["To"] = recipient

    server.send_message(message)

    print("TEST EMAIL SENT SUCCESSFULLY.")

except Exception as e:
    print("\nTEST FAILED")
    print("Error type:", type(e).__name__)
    print("Error:", repr(e))

finally:
    if server:
        try:
            server.quit()
        except Exception:
            pass
