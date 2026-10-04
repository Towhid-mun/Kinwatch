import smtplib
from email.message import EmailMessage

import config


def send_unknown_person_alert(to_addr, image_path, ts):
    if not config.SMTP_USERNAME or not config.SMTP_PASSWORD:
        raise RuntimeError(
            "SMTP_USERNAME/SMTP_PASSWORD not set in security/.env - "
            "can't send alert email"
        )

    msg = EmailMessage()
    msg["Subject"] = "Home security: unknown person detected"
    msg["From"] = config.SMTP_USERNAME
    msg["To"] = to_addr
    msg.set_content(
        f"An unrecognized person was detected at {ts}.\n\n"
        "See the attached snapshot."
    )
    with open(image_path, "rb") as f:
        msg.add_attachment(
            f.read(), maintype="image", subtype="jpeg", filename="unknown_person.jpg"
        )

    with smtplib.SMTP(config.SMTP_HOST, config.SMTP_PORT) as smtp:
        smtp.starttls()
        smtp.login(config.SMTP_USERNAME, config.SMTP_PASSWORD)
        smtp.send_message(msg)
