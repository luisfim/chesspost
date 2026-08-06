from dataclasses import dataclass
import base64
import html
import os
from pathlib import Path

import resend

from email_gateway import OutgoingEmail


INLINE_BOARD_CONTENT_ID = "chess-board"


@dataclass(frozen=True)
class DeliveryResult:
    recipient: str
    mode: str
    provider_id: str | None
    scheduled: bool


def create_html_body(
    body: str,
    include_board: bool,
) -> str:
    """Convert a plain-text Chesspost email into simple HTML."""
    paragraphs: list[str] = []

    for paragraph in body.split("\n\n"):
        paragraph = paragraph.strip()

        if not paragraph:
            continue

        escaped_paragraph = html.escape(paragraph).replace(
            "\n",
            "<br>",
        )
        paragraphs.append(f"<p>{escaped_paragraph}</p>")

    if include_board:
        paragraphs.append(
            (
                '<p style="margin-top: 24px;">'
                '<img src="cid:chess-board" '
                'alt="Current chess position" '
                'width="600" '
                'style="display:block;max-width:100%;height:auto;">'
                "</p>"
            )
        )

    return "\n".join(paragraphs)


def create_board_attachment(
    attachment_path: Path,
) -> dict[str, str]:
    """Read a local board PNG and prepare it for Resend."""
    if not attachment_path.exists():
        raise FileNotFoundError(
            f"Board attachment not found: {attachment_path}"
        )

    encoded_content = base64.b64encode(
        attachment_path.read_bytes()
    ).decode("ascii")

    return {
        "content": encoded_content,
        "filename": "chesspost-board.png",
        "content_id": INLINE_BOARD_CONTENT_ID,
    }


def build_resend_params(
    email: OutgoingEmail,
    sender_address: str,
) -> dict[str, object]:
    """Convert a Chesspost outgoing email into Resend parameters."""
    include_board = email.attachment_path is not None

    params: dict[str, object] = {
        "from": sender_address,
        "to": [email.recipient],
        "subject": email.subject,
        "text": email.body,
        "html": create_html_body(
            body=email.body,
            include_board=include_board,
        ),
    }

    if email.reply_address is not None:
        params["reply_to"] = email.reply_address

    if email.headers:
        params["headers"] = dict(email.headers)

    if email.attachment_path is not None:
        params["attachments"] = [
            create_board_attachment(email.attachment_path)
        ]

    if email.delay_hours > 0:
        params["scheduled_at"] = (
            f"in {email.delay_hours} hours"
        )

    return params


def extract_provider_id(response: object) -> str | None:
    """Extract the provider email ID from different response shapes."""
    if isinstance(response, dict):
        response_id = response.get("id")
        return str(response_id) if response_id is not None else None

    response_id = getattr(response, "id", None)

    if response_id is None:
        return None

    return str(response_id)


def parse_real_recipients(
    value: str | None,
) -> set[str]:
    """Parse the addresses allowed to receive real test emails."""
    if not value:
        return set()

    return {
        address.strip().lower()
        for address in value.split(",")
        if address.strip()
    }


def send_with_resend(
    email: OutgoingEmail,
) -> DeliveryResult:
    """Send one email through Resend."""
    api_key = os.getenv("RESEND_API_KEY")

    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY is required in Resend mode."
        )

    sender_address = os.getenv("CHESSPOST_FROM_EMAIL")

    if not sender_address:
        raise RuntimeError(
            "CHESSPOST_FROM_EMAIL is required in Resend mode."
        )

    resend.api_key = api_key

    params = build_resend_params(
        email=email,
        sender_address=sender_address,
    )

    response = resend.Emails.send(params)

    return DeliveryResult(
        recipient=email.recipient,
        mode="resend",
        provider_id=extract_provider_id(response),
        scheduled=email.delay_hours > 0,
    )


def print_console_email(email: OutgoingEmail) -> None:
    """Print an outgoing email without sending it."""
    print()
    print("=" * 70)
    print("CHESSPOST OUTGOING EMAIL")
    print(f"TO: {email.recipient}")
    print(f"SUBJECT: {email.subject}")
    print(f"REPLY-TO: {email.reply_address or '-'}")
    print(f"DELAY: {email.delay_hours} hour(s)")
    print(f"ATTACHMENT: {email.attachment_path or '-'}")
    print()
    print(email.body)
    print("=" * 70)


def send_outgoing_email(
    email: OutgoingEmail,
    mode: str | None = None,
) -> DeliveryResult:
    """Send, simulate, or selectively deliver one email."""
    selected_mode = (
        mode
        or os.getenv("CHESSPOST_EMAIL_MODE", "console")
    ).strip().lower()

    if selected_mode == "console":
        print_console_email(email)

        return DeliveryResult(
            recipient=email.recipient,
            mode="console",
            provider_id=None,
            scheduled=email.delay_hours > 0,
        )

    if selected_mode == "hybrid":
        allowed_recipients = parse_real_recipients(
            os.getenv("CHESSPOST_REAL_RECIPIENTS")
        )

        if email.recipient.strip().lower() not in allowed_recipients:
            print_console_email(email)

            return DeliveryResult(
                recipient=email.recipient,
                mode="console",
                provider_id=None,
                scheduled=email.delay_hours > 0,
            )

        return send_with_resend(email)

    if selected_mode == "resend":
        return send_with_resend(email)

    raise ValueError(
        "CHESSPOST_EMAIL_MODE must be "
        '"console", "hybrid", or "resend".'
    )

def dispatch_outgoing_emails(
    emails: tuple[OutgoingEmail, ...],
    mode: str | None = None,
) -> tuple[DeliveryResult, ...]:
    """Deliver every email prepared by the gateway."""
    return tuple(
        send_outgoing_email(email, mode=mode)
        for email in emails
    )
