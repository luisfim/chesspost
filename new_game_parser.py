from dataclasses import dataclass
import re

from email_parser import extract_new_lines


EMAIL_PATTERN = re.compile(
    r"^[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+"
    r"@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?"
    r"(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class NewGameRequest:
    valid: bool
    sender_email: str
    opponent_email: str | None
    color: str
    delay_hours: int
    message: str


def is_valid_email(address: str) -> bool:
    """Perform basic validation of an email address."""
    return EMAIL_PATTERN.fullmatch(address.strip()) is not None


def parse_color(line: str) -> str | None:
    """Parse a color setting such as 'color: white'."""
    match = re.fullmatch(
        r"color\s*:\s*(white|black|random)",
        line.strip(),
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    return match.group(1).lower()


def parse_starting_delay(line: str) -> int | None:
    """Parse immediate delivery or a delay between 1 and 720 hours."""
    match = re.fullmatch(
        r"delay\s*:\s*(.+)",
        line.strip(),
        flags=re.IGNORECASE,
    )

    if match is None:
        return None

    value = match.group(1).strip().lower()

    if value in {"immediate", "immediately", "now", "0h"}:
        return 0

    hours_match = re.fullmatch(
        r"(\d+)\s*(?:h|hour|hours)",
        value,
        flags=re.IGNORECASE,
    )

    if hours_match is None:
        return None

    hours = int(hours_match.group(1))

    if hours < 1 or hours > 720:
        return None

    return hours


def parse_new_game_email(
    sender_email: str,
    subject: str,
    body: str,
) -> NewGameRequest:
    """Parse an email sent to the main Chesspost address."""
    sender_email = sender_email.strip().lower()
    opponent_email = subject.strip().lower()

    if not is_valid_email(sender_email):
        return NewGameRequest(
            valid=False,
            sender_email=sender_email,
            opponent_email=None,
            color="random",
            delay_hours=0,
            message="The sender email address is invalid.",
        )

    if not is_valid_email(opponent_email):
        return NewGameRequest(
            valid=False,
            sender_email=sender_email,
            opponent_email=None,
            color="random",
            delay_hours=0,
            message=(
                "The subject must contain the opponent's email address."
            ),
        )

    if sender_email == opponent_email:
        return NewGameRequest(
            valid=False,
            sender_email=sender_email,
            opponent_email=opponent_email,
            color="random",
            delay_hours=0,
            message="You cannot start a game against your own email address.",
        )

    color = "random"
    delay_hours = 0

    for line in extract_new_lines(body):
        normalized_line = line.strip().lower()

        if normalized_line.startswith("color"):
            parsed_color = parse_color(line)

            if parsed_color is None:
                return NewGameRequest(
                    valid=False,
                    sender_email=sender_email,
                    opponent_email=opponent_email,
                    color=color,
                    delay_hours=delay_hours,
                    message=(
                        'Color must be "white", "black", or "random".'
                    ),
                )

            color = parsed_color

        elif normalized_line.startswith("delay"):
            parsed_delay = parse_starting_delay(line)

            if parsed_delay is None:
                return NewGameRequest(
                    valid=False,
                    sender_email=sender_email,
                    opponent_email=opponent_email,
                    color=color,
                    delay_hours=delay_hours,
                    message=(
                        "Delay must be immediate or between 1 and 720 hours."
                    ),
                )

            delay_hours = parsed_delay

    return NewGameRequest(
        valid=True,
        sender_email=sender_email,
        opponent_email=opponent_email,
        color=color,
        delay_hours=delay_hours,
        message="New game request accepted.",
    )
