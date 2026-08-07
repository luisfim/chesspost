from dataclasses import dataclass
from pathlib import Path
import re

from database import DATABASE_PATH, get_game
from email_service import (
    DEFAULT_ATTACHMENT_DIRECTORY,
    create_board_attachment,
    error_response,
    process_game_email,
)
from email_parser import parse_email_body
from draw_service import (
    accept_draw,
    clear_draw_offer,
    decline_draw,
    get_draw_offer,
    offer_draw,
)
from game_service import resign_game
from game_summary import (
    build_final_email_body,
    summarize_game,
)
from invitation_decision_service import process_invitation_reply
from invitation_service import (
    GAME_EMAIL_DOMAIN,
    process_new_game_email,
    process_rematch_request,
)


MAIN_EMAIL_ADDRESS = f"play@{GAME_EMAIL_DOMAIN}"

GAME_ADDRESS_PATTERN = re.compile(
    rf"^game-([a-f0-9]{{16}})@{re.escape(GAME_EMAIL_DOMAIN)}$",
    flags=re.IGNORECASE,
)


@dataclass(frozen=True)
class OutgoingEmail:
    recipient: str
    subject: str
    body: str
    reply_address: str | None
    attachment_path: Path | None
    delay_hours: int
    headers: dict[str, str] | None = None


@dataclass(frozen=True)
class GatewayResult:
    route: str
    processed: bool
    game_code: str | None
    emails: tuple[OutgoingEmail, ...]


def create_gateway_error(
    sender_email: str,
    message: str,
) -> GatewayResult:
    """Create an error response for an unknown recipient address."""
    email = OutgoingEmail(
        recipient=sender_email.strip().lower(),
        subject="[Chesspost] Email could not be processed",
        body=message,
        reply_address=None,
        attachment_path=None,
        delay_hours=0,
    )

    return GatewayResult(
        route="unknown",
        processed=False,
        game_code=None,
        emails=(email,),
    )


def extract_game_code(recipient_email: str) -> str | None:
    """Extract a game code from a Chesspost game address."""
    match = GAME_ADDRESS_PATTERN.fullmatch(
        recipient_email.strip().lower()
    )

    if match is None:
        return None

    return match.group(1).lower()


def build_finished_game_emails(
    *,
    game,
    attachment_directory: Path,
    db_path: Path,
    delay_hours: int = 0,
    termination_override: str | None = None,
) -> tuple[OutgoingEmail, ...]:
    """Prepare the final game report for both players."""
    summary = summarize_game(
        game,
        db_path,
        termination_override=termination_override,
    )

    body = build_final_email_body(
        game,
        summary,
    )

    short_code = game.code[:8].upper()
    emails: list[OutgoingEmail] = []

    for player_email in (
        game.white_email,
        game.black_email,
    ):
        board_path = create_board_attachment(
            game=game,
            recipient_email=player_email,
            attachment_directory=attachment_directory,
        )

        emails.append(
            OutgoingEmail(
                recipient=player_email,
                subject=(
                    f"[Chesspost {short_code}] "
                    f"Game over — {game.result}"
                ),
                body=body,
                reply_address=(
                    f"game-{game.code}@{GAME_EMAIL_DOMAIN}"
                ),
                attachment_path=board_path,
                delay_hours=delay_hours,
            )
        )

    return tuple(emails)


def process_incoming_email(
    *,
    sender_email: str,
    recipient_email: str,
    subject: str,
    body: str,
    db_path: Path = DATABASE_PATH,
    attachment_directory: Path = DEFAULT_ATTACHMENT_DIRECTORY,
) -> GatewayResult:
    """Route an incoming email to the correct Chesspost service."""
    sender_email = sender_email.strip().lower()
    recipient_email = recipient_email.strip().lower()

    if recipient_email == MAIN_EMAIL_ADDRESS:
        invitation = process_new_game_email(
            sender_email=sender_email,
            subject=subject,
            body=body,
            db_path=db_path,
        )

        outgoing_email = OutgoingEmail(
            recipient=invitation.recipient,
            subject=invitation.subject,
            body=invitation.body,
            reply_address=invitation.reply_address,
            attachment_path=None,
            delay_hours=0,
        )

        game_code = (
            invitation.game.code
            if invitation.game is not None
            else None
        )

        return GatewayResult(
            route="new_game",
            processed=invitation.request_accepted,
            game_code=game_code,
            emails=(outgoing_email,),
        )

    game_code = extract_game_code(recipient_email)

    if game_code is None:
        return create_gateway_error(
            sender_email,
            (
                "This is not a recognized Chesspost email address.\n\n"
                f"To start a new game, email {MAIN_EMAIL_ADDRESS} "
                "and put your opponent's email address in the subject."
            ),
        )

    game = get_game(game_code, db_path)

    if game is not None and game.status == "invited":
        decision = process_invitation_reply(
            game_code=game_code,
            sender_email=sender_email,
            email_body=body,
            db_path=db_path,
        )

        outgoing_emails = tuple(
            OutgoingEmail(
                recipient=email.recipient,
                subject=email.subject,
                body=email.body,
                reply_address=email.reply_address,
                attachment_path=None,
                delay_hours=0,
            )
            for email in decision.emails
        )

        return GatewayResult(
            route="invitation_reply",
            processed=decision.processed,
            game_code=game_code,
            emails=outgoing_emails,
        )

    parsed_email = parse_email_body(body)

    if (
        parsed_email.valid
        and parsed_email.command == "offer_draw"
    ):
        draw_result = offer_draw(
            game_code,
            sender_email,
            db_path,
        )

        if not draw_result.accepted:
            response = error_response(
                sender_email,
                game_code,
                draw_result.message,
            )

            return GatewayResult(
                route="game_message",
                processed=False,
                game_code=game_code,
                emails=(
                    OutgoingEmail(
                        recipient=response.recipient,
                        subject=response.subject,
                        body=response.body,
                        reply_address=recipient_email,
                        attachment_path=None,
                        delay_hours=0,
                    ),
                ),
            )

        opponent = (
            game.black_email
            if sender_email == game.white_email
            else game.white_email
        )

        return GatewayResult(
            route="draw_offer",
            processed=True,
            game_code=game_code,
            emails=(
                OutgoingEmail(
                    recipient=opponent,
                    subject=f"[Chesspost {game_code[:8].upper()}] Draw offer",
                    body=(
                        f"{sender_email} offered a draw.\n\n"
                        "Reply with:\n\n"
                        "accept draw\n\n"
                        "or:\n\n"
                        "decline draw\n\n"
                        "You may also make your next move to "
                        "decline the offer automatically."
                    ),
                    reply_address=recipient_email,
                    attachment_path=None,
                    delay_hours=0,
                ),
            ),
        )

    if (
        parsed_email.valid
        and parsed_email.command == "accept_draw"
    ):
        draw_result = accept_draw(
            game_code,
            sender_email,
            db_path,
        )

        if not draw_result.accepted:
            response = error_response(
                sender_email,
                game_code,
                draw_result.message,
            )

            return GatewayResult(
                route="game_message",
                processed=False,
                game_code=game_code,
                emails=(
                    OutgoingEmail(
                        recipient=response.recipient,
                        subject=response.subject,
                        body=response.body,
                        reply_address=recipient_email,
                        attachment_path=None,
                        delay_hours=0,
                    ),
                ),
            )

        return GatewayResult(
            route="game_finished",
            processed=True,
            game_code=game_code,
            emails=build_finished_game_emails(
                game=draw_result.game,
                attachment_directory=attachment_directory,
                db_path=db_path,
                termination_override="Draw agreed",
            ),
        )

    if (
        parsed_email.valid
        and parsed_email.command == "decline_draw"
    ):
        draw_result = decline_draw(
            game_code,
            sender_email,
            db_path,
        )

        if not draw_result.accepted:
            response = error_response(
                sender_email,
                game_code,
                draw_result.message,
            )

            return GatewayResult(
                route="game_message",
                processed=False,
                game_code=game_code,
                emails=(
                    OutgoingEmail(
                        recipient=response.recipient,
                        subject=response.subject,
                        body=response.body,
                        reply_address=recipient_email,
                        attachment_path=None,
                        delay_hours=0,
                    ),
                ),
            )

        offerer = (
            game.black_email
            if sender_email == game.white_email
            else game.white_email
        )

        return GatewayResult(
            route="draw_declined",
            processed=True,
            game_code=game_code,
            emails=(
                OutgoingEmail(
                    recipient=offerer,
                    subject=f"[Chesspost {game_code[:8].upper()}] Draw declined",
                    body=(
                        f"{sender_email} declined the draw offer.\n\n"
                        "The game continues."
                    ),
                    reply_address=recipient_email,
                    attachment_path=None,
                    delay_hours=0,
                ),
            ),
        )

    # Making a move implicitly declines the opponent's draw offer.
    if (
        parsed_email.valid
        and parsed_email.command == "move"
    ):
        pending_offer = get_draw_offer(
            game_code,
            db_path,
        )

        if (
            pending_offer is not None
            and pending_offer.offered_by_email != sender_email
        ):
            clear_draw_offer(
                game_code,
                db_path,
            )

    if (
        parsed_email.valid
        and parsed_email.command == "rematch"
    ):
        rematch = process_rematch_request(
            previous_game=game,
            sender_email=sender_email,
            db_path=db_path,
        )

        if (
            not rematch.request_accepted
            or rematch.game is None
        ):
            response = error_response(
                sender_email,
                game_code,
                rematch.body,
            )

            return GatewayResult(
                route="game_message",
                processed=False,
                game_code=game_code,
                emails=(
                    OutgoingEmail(
                        recipient=response.recipient,
                        subject=response.subject,
                        body=response.body,
                        reply_address=recipient_email,
                        attachment_path=None,
                        delay_hours=0,
                    ),
                ),
            )

        return GatewayResult(
            route="rematch",
            processed=True,
            game_code=rematch.game.code,
            emails=(
                OutgoingEmail(
                    recipient=rematch.recipient,
                    subject=rematch.subject,
                    body=rematch.body,
                    reply_address=rematch.reply_address,
                    attachment_path=None,
                    delay_hours=0,
                ),
            ),
        )

    if (
        parsed_email.valid
        and parsed_email.command == "resign"
    ):
        resignation = resign_game(
            game_code=game_code,
            sender_email=sender_email,
            db_path=db_path,
        )

        if not resignation.accepted:
            response = error_response(
                sender_email,
                game_code,
                resignation.message,
            )

            return GatewayResult(
                route="game_message",
                processed=False,
                game_code=game_code,
                emails=(
                    OutgoingEmail(
                        recipient=response.recipient,
                        subject=response.subject,
                        body=response.body,
                        reply_address=recipient_email,
                        attachment_path=None,
                        delay_hours=0,
                    ),
                ),
            )

        return GatewayResult(
            route="game_finished",
            processed=True,
            game_code=game_code,
            emails=build_finished_game_emails(
                game=resignation.game,
                attachment_directory=attachment_directory,
                db_path=db_path,
                termination_override="Resignation",
            ),
        )

    move_response = process_game_email(
        game_code=game_code,
        sender_email=sender_email,
        email_body=body,
        db_path=db_path,
        attachment_directory=attachment_directory,
    )

    if move_response.delivered_to_opponent:
        updated_game = get_game(
            game_code,
            db_path,
        )

        if (
            updated_game is not None
            and updated_game.status == "finished"
        ):
            return GatewayResult(
                route="game_finished",
                processed=True,
                game_code=game_code,
                emails=build_finished_game_emails(
                    game=updated_game,
                    attachment_directory=attachment_directory,
                    db_path=db_path,
                    delay_hours=move_response.delay_hours or 0,
                ),
            )

    outgoing_email = OutgoingEmail(
        recipient=move_response.recipient,
        subject=move_response.subject,
        body=move_response.body,
        reply_address=recipient_email,
        attachment_path=move_response.attachment_path,
        delay_hours=move_response.delay_hours or 0,
    )

    return GatewayResult(
        route="game_message",
        processed=move_response.delivered_to_opponent,
        game_code=game_code,
        emails=(outgoing_email,),
    )
