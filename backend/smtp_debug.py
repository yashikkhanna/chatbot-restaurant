
import os
import ssl
import socket
import smtplib
import traceback

from pathlib import Path
from dotenv import load_dotenv
from email.mime.text import MIMEText


# ==========================================
# 1. LOAD ENVIRONMENT VARIABLES
# ==========================================

BASE_DIR = Path(__file__).resolve().parent
ENV_PATH = BASE_DIR.parent / ".env"

load_dotenv(ENV_PATH)

EMAIL_USER = os.getenv("EMAIL_USER")
EMAIL_PASSWORD = os.getenv("EMAIL_PASSWORD")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

print("\n========== SMTP DEBUG START ==========")

print("[1] ENVIRONMENT CHECK")

print("ENV FILE EXISTS:", ENV_PATH.exists())
print("EMAIL_USER LOADED:", bool(EMAIL_USER))
print("EMAIL_PASSWORD LOADED:", bool(EMAIL_PASSWORD))


if not EMAIL_USER or not EMAIL_PASSWORD:
    raise SystemExit("ERROR: Email credentials are missing.")


# ==========================================
# 2. DNS RESOLUTION
# ==========================================

print("\n[2] DNS RESOLUTION")

try:
    addresses = socket.getaddrinfo(
        SMTP_HOST,
        SMTP_PORT,
        type=socket.SOCK_STREAM
    )

    for address in addresses:
        print(
            "Resolved:",
            "IPv4" if address[0] == socket.AF_INET else "IPv6",
            address[4][0]
        )

    print("DNS RESOLUTION SUCCESSFUL")

except Exception as e:
    print("DNS ERROR:", repr(e))
    traceback.print_exc()
    raise SystemExit()


# ==========================================
# 3. SSL CONNECTION
# ==========================================

print("\n[3] CONNECTING TO GMAIL SMTP")

server = None
stage = "Connection initialization"

try:

    context = ssl.create_default_context()

    stage = "TCP and SSL connection"

    server = smtplib.SMTP_SSL(
        SMTP_HOST,
        SMTP_PORT,
        context=context,
        timeout=30
    )

    print("SSL CONNECTION SUCCESSFUL")

    # ======================================
    # 4. SMTP GREETING
    # ======================================

    stage = "SMTP EHLO greeting"

    print("\n[4] CHECKING SMTP GREETING")

    response = server.ehlo()

    print("EHLO RESPONSE CODE:", response[0])
    print("EHLO RESPONSE:", response[1].decode(errors="replace"))

    # ======================================
    # 5. SMTP AUTHENTICATION
    # ======================================

    stage = "Gmail authentication"

    print("\n[5] AUTHENTICATING WITH GMAIL")

    server.login(EMAIL_USER, EMAIL_PASSWORD)

    print("GMAIL AUTHENTICATION SUCCESSFUL")

    # ======================================
    # 6. SEND TEST EMAIL
    # ======================================

    stage = "Sending test email"

    print("\n[6] SENDING TEST EMAIL")

    test_email = input(
        "Enter your email address to receive a test email: "
    ).strip()

    message = MIMEText(
        "SMTP diagnostic successful. Gmail email delivery is working.",
        "plain"
    )

    message["Subject"] = "SMTP Diagnostic Test"
    message["From"] = EMAIL_USER
    message["To"] = test_email

    server.send_message(message)

    print("TEST EMAIL SENT SUCCESSFULLY")

except Exception as e:

    print("\n========== SMTP ERROR ==========")

    print("FAILED STAGE:", stage)
    print("ERROR TYPE:", type(e).__name__)
    print("ERROR MESSAGE:", repr(e))

    print("\nFULL TRACEBACK:")

    traceback.print_exc()

finally:

    if server is not None:

        try:
            server.quit()
            print("\nSMTP CONNECTION CLOSED CLEANLY")

        except Exception as e:
            print("SMTP CLOSE WARNING:", repr(e))


print("\n========== SMTP DEBUG END ==========")
