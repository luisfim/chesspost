from dataclasses import dataclass
from email.utils import parseaddr
from html.parser import HTMLParser
import os
import re
from typing import Any, Mapping

import resend
from svix.webhooks import Webhook


@dataclass(frozen=True)
class ReceivedEmail:
    email_id: str
    sender_email: str
    recipient_email: str
    subject: str
    body: str
    message_id: str = ""
    references: tuple[str, ...] = ()


class PlainTextHTMLParser(HTMLParser):
    """Extract readable plain text from a simple HTML email."""

    BLOCK_TAGS = {
        "br",
        "div",
        "p",
        "li",
        "tr",
        "h1",
        "h2",
        "h3",
        "h4",
        "h5",
        "h6",
    }

    IGNORED_TAGS = {
        "script",
        "style",
    }

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []
        self.ignored_depth = 0

    def handle_starttag(
        self,
        tag: str,
        attrs: list[tuple[str, str | None]],
    ) -> None:
        normalized_tag = tag.lower()

        if normalized_tag in self.IGNORED_TAGS:
            self.ignored_depth += 1
            return

        if (
            self.ignored_depth == 0
            and normalized_tag in self.BLOCK_TAGS
        ):
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        normalized_tag = tag.lower()

        if normalized_tag in self.IGNORED_TAGS:
            if self.ignored_depth > 0:
                self.ignored_depth -= 1
            return

        if (
            self.ignored_depth == 0
            and normalized_tag in self.BLOCK_TAGS
        ):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self.ignored_depth == 0:
            self.parts.append(data)

    def get_text(self) -> str:
        lines = [
            line.strip()
            for line in "".join(self.parts).splitlines()
        ]

        cleaned_lines: list[str] = []
        previous_was_empty = False

        for line in lines:
            if not line:
                if cleaned_lines and not previous_was_empty:
                    cleaned_lines.append("")

                previous_was_empty = True
                continue

            cleaned_lines.append(line)
            previous_was_empty = False

        return "\n".join(cleaned_lines).strip()


def html_to_text(html_body: str) -> str:
    """Convert an HTML-only email into readable text."""
    parser = PlainTextHTMLParser()
    parser.feed(html_body)
    parser.close()

    return parser.get_text()


def get_field(
    value: Any,
    field_name: str,
    default: Any = None,
) -> Any:
    """Read a field from either a dictionary or SDK object."""
    if isinstance(value, dict):
        return value.get(field_name, default)

    return getattr(value, field_name, default)


def get_header(
    headers: Any,
    header_name: str,
) -> Any:
    """Read an email header without depending on capitalization."""
    if not isinstance(headers, Mapping):
        return None

    normalized_name = header_name.strip().lower()

    for key, value in headers.items():
        if str(key).strip().lower() == normalized_name:
            return value

    return None


def normalize_message_references(
    values: Any,
) -> tuple[str, ...]:
    """Normalize and deduplicate email Message-ID references."""
    if values is None:
        return ()

    if isinstance(values, (list, tuple)):
        parts = [str(value) for value in values if value]
        combined = " ".join(parts)
    else:
        combined = str(values)

    message_ids = re.findall(r"<[^<>]+>", combined)

    if not message_ids:
        message_ids = combined.split()

    normalized: list[str] = []

    for message_id in message_ids:
        message_id = message_id.strip()

        if message_id and message_id not in normalized:
            normalized.append(message_id)

    return tuple(normalized)


def normalize_email_address(value: str) -> str:
    """Extract and normalize an address such as 'Luis <a@example.com>'."""
    _, parsed_address = parseaddr(value)
    normalized = parsed_address.strip().lower()

    if not normalized:
        normalized = value.strip().lower()

    return normalized


def verify_resend_event(
    raw_payload: bytes,
    headers: Mapping[str, str],
    webhook_secret: str,
) -> dict[str, Any]:
    """Verify a Resend webhook using its raw request body."""
    required_headers = {
        "svix-id": headers.get("svix-id", ""),
        "svix-timestamp": headers.get("svix-timestamp", ""),
        "svix-signature": headers.get("svix-signature", ""),
    }

    if not all(required_headers.values()):
        raise ValueError("Missing Resend webhook signature headers.")

    webhook = Webhook(webhook_secret)
    event = webhook.verify(raw_payload, required_headers)

    if not isinstance(event, dict):
        raise ValueError("The verified webhook payload is invalid.")

    return event


def get_received_email_id(
    event: Mapping[str, Any],
) -> str | None:
    """Extract the received email ID from a webhook event."""
    if event.get("type") != "email.received":
        return None

    data = event.get("data")

    if not isinstance(data, Mapping):
        raise ValueError("The webhook event does not contain email data.")

    email_id = data.get("email_id")

    if not isinstance(email_id, str) or not email_id.strip():
        raise ValueError("The webhook event does not contain an email ID.")

    return email_id.strip()


def fetch_received_email(
    email_id: str,
    api_key: str | None = None,
    fallback_message_id: str | None = None,
) -> ReceivedEmail:
    """Retrieve the complete body of an inbound email from Resend."""
    selected_api_key = (
        api_key
        or os.getenv("RESEND_API_KEY")
    )

    if not selected_api_key:
        raise RuntimeError(
            "RESEND_API_KEY is required to retrieve inbound emails."
        )

    resend.api_key = selected_api_key

    response = resend.Emails.Receiving.get(
        email_id=email_id,
    )

    sender_value = str(get_field(response, "from", ""))
    recipients = get_field(response, "to", [])
    subject = str(get_field(response, "subject", "") or "")
    text_body = get_field(response, "text")
    html_body = get_field(response, "html")
    headers = get_field(response, "headers", {})

    message_id = str(
        get_field(response, "message_id", "")
        or get_header(headers, "message-id")
        or fallback_message_id
        or ""
    ).strip()

    references = normalize_message_references(
        [
            get_header(headers, "references"),
            get_header(headers, "in-reply-to"),
        ]
    )

    if not sender_value:
        raise ValueError("The received email does not contain a sender.")

    if not isinstance(recipients, list) or not recipients:
        raise ValueError("The received email does not contain a recipient.")

    if text_body:
        body = str(text_body)
    elif html_body:
        body = html_to_text(str(html_body))
    else:
        body = ""

    return ReceivedEmail(
        email_id=email_id,
        sender_email=normalize_email_address(sender_value),
        recipient_email=normalize_email_address(
            str(recipients[0])
        ),
        subject=subject,
        body=body,
        message_id=message_id,
        references=references,
    )
