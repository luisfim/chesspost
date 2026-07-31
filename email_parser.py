from dataclasses import dataclass
import re


SUPPORTED_COMMANDS = {
    "accept",
    "decline",
    "resign",
    "rematch",
    "help",
    "show board",
    "show moves",
    "offer draw",
    "accept draw",
    "decline draw",
}


@dataclass(frozen=True)
class ParsedEmail:
    valid: bool
    command: str | None
    value: str | None
    delay_hours: int | None
    message: str


def extract_new_lines(body: str) -> list[str]:
    """Extract only the newly written part of an email reply."""
    new_lines: list[str] = []

    for raw_line in body.splitlines():
        line = raw_line.strip()

        # Standard email signature delimiter.
        if line in {"--", "-- "}:
            break

        # Quoted previous messages.
        if line.startswith(">"):
            break

        lower_line = line.lower()

        # Common English and Portuguese reply headers.
        if lower_line.startswith("on ") and lower_line.endswith("wrote:"):
            break

        if lower_line.startswith("em ") and (
            "escreveu:" in lower_line or "wrote:" in lower_line
        ):
            break

        if line:
            new_lines.append(line)

    return new_lines


def parse_delay(line: str) -> int | None:
    """Parse a line such as 'delay: 24h'."""
    match = re.fullmatch(
        r"delay\s*:\s*(\d+)\s*(?:h|hour|hours)",
        line,
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    delay_hours = int(match.group(1))

    if delay_hours < 1 or delay_hours > 720:
        return None

    return delay_hours


def parse_email_body(body: str) -> ParsedEmail:
    """Parse a chess move or command from an email body."""
    lines = extract_new_lines(body)

    if not lines:
        return ParsedEmail(
            valid=False,
            command=None,
            value=None,
            delay_hours=None,
            message="The email did not contain a move or command.",
        )

    first_line = lines[0].strip()
    normalized_first_line = first_line.lower()
    delay_hours: int | None = None

    for line in lines[1:]:
        parsed_delay = parse_delay(line)

        if parsed_delay is not None:
            delay_hours = parsed_delay
            break

    if normalized_first_line in SUPPORTED_COMMANDS:
        return ParsedEmail(
            valid=True,
            command=normalized_first_line.replace(" ", "_"),
            value=None,
            delay_hours=delay_hours,
            message=f"Command recognized: {normalized_first_line}",
        )

    return ParsedEmail(
        valid=True,
        command="move",
        value=first_line,
        delay_hours=delay_hours,
        message=f"Move received: {first_line}",
    )
