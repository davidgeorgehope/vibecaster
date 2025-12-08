"""
Email notifications via Gmail SMTP.

Setup:
1. Enable 2-Step Verification on your Google account
2. Go to https://myaccount.google.com/apppasswords
3. Create an App Password for "Mail"
4. Add to .env:
   ADMIN_EMAIL=email.djhope@gmail.com
   SMTP_PASSWORD=your_16_char_app_password
"""

import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from logger_config import app_logger as logger

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "email.djhope@gmail.com")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD")


def send_signup_notification(user_email: str, user_id: int):
    """Send email notification when a new user signs up."""
    if not SMTP_PASSWORD:
        logger.warning("SMTP_PASSWORD not configured - skipping signup notification")
        return False

    try:
        # Create message
        msg = MIMEMultipart()
        msg["From"] = ADMIN_EMAIL
        msg["To"] = ADMIN_EMAIL
        msg["Subject"] = f"🎉 New Vibecaster Signup: {user_email}"

        body = f"""
New user signed up for Vibecaster!

Email: {user_email}
User ID: {user_id}

View all users at your admin dashboard.
"""
        msg.attach(MIMEText(body, "plain"))

        # Send via Gmail SMTP
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as server:
            server.login(ADMIN_EMAIL, SMTP_PASSWORD)
            server.sendmail(ADMIN_EMAIL, ADMIN_EMAIL, msg.as_string())

        logger.info(f"Signup notification sent for user: {user_email}")
        return True

    except Exception as e:
        logger.error(f"Failed to send signup notification: {e}")
        return False
