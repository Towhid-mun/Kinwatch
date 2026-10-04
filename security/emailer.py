import smtplib
import socket
from email.message import EmailMessage

import config

SMTP_TIMEOUT_SECONDS = 20


def _new_message(to_addr, subject, body):
    if not config.EMAIL_ADDRESS or not config.EMAIL_APP_PASSWORD:
        raise RuntimeError(
            "EMAIL_ADDRESS/EMAIL_APP_PASSWORD not set in security/.env - "
            "can't send email"
        )
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = config.EMAIL_ADDRESS
    msg["To"] = to_addr
    msg.set_content(body)
    return msg


def _send(msg):
    """Port 465 is implicit TLS (SMTP_SSL); anything else (587 for Gmail)
    is plain SMTP upgraded with STARTTLS. Re-raises with a hint for the
    errors a misconfigured Gmail account actually produces."""
    try:
        if config.SMTP_PORT == 465:
            smtp = smtplib.SMTP_SSL(config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
        else:
            smtp = smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT, timeout=SMTP_TIMEOUT_SECONDS)
        with smtp:
            if config.SMTP_PORT != 465:
                smtp.ehlo()
                smtp.starttls()
                smtp.ehlo()
            # AUTH LOGIN explicitly, not smtp.login(): login() picks AUTH
            # PLAIN first, and Gmail answers a failed PLAIN by dropping the
            # connection ("Connection unexpectedly closed") instead of
            # returning the 535 bad-credentials reply LOGIN gets.
            smtp.user, smtp.password = config.EMAIL_ADDRESS, config.EMAIL_APP_PASSWORD
            smtp.auth("LOGIN", smtp.auth_login)
            smtp.send_message(msg)
    except smtplib.SMTPAuthenticationError as exc:
        raise RuntimeError(
            f"login rejected for {config.EMAIL_ADDRESS} - check EMAIL_ADDRESS is "
            "spelled correctly and EMAIL_APP_PASSWORD is a Google App Password "
            f"(not the account password) ({exc.smtp_code} {exc.smtp_error.decode(errors='replace')})"
        ) from exc
    except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, socket.timeout, socket.gaierror, ConnectionError) as exc:
        raise RuntimeError(
            f"could not talk to {config.SMTP_HOST}:{config.SMTP_PORT} - {exc}"
        ) from exc


def send_unknown_person_alert(to_addr, image_path, ts):
    msg = _new_message(
        to_addr,
        "Home security: unknown person detected",
        f"An unrecognized person was detected at {ts}.\n\nSee the attached snapshot.",
    )
    with open(image_path, "rb") as f:
        msg.add_attachment(
            f.read(), maintype="image", subtype="jpeg", filename="unknown_person.jpg"
        )
    _send(msg)


def send_test_email(to_addr, ts):
    msg = _new_message(
        to_addr,
        "Home security: test email",
        f"This is a test email from your Kinwatch home security system, sent at {ts}.\n\n"
        "If you received it, alert emails are configured correctly.",
    )
    _send(msg)
