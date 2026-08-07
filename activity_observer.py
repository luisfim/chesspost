from pathlib import Path

from activity_log import log_activity
from email_parser import parse_email_body


def record_received_email(
    received_email,
    db_path: Path,
) -> None:
    log_activity(
        "email_received",
        actor_email=received_email.sender_email,
        target_email=received_email.recipient_email,
        detail="Inbound email received",
        db_path=db_path,
    )


def record_gateway_result(
    result,
    received_email,
    db_path: Path,
) -> None:
    """Translate a gateway result into a human-readable activity event."""
    try:
        parsed = parse_email_body(
            received_email.body
        )
    except Exception:
        parsed = None

    command = (
        parsed.command
        if parsed is not None and parsed.valid
        else None
    )

    value = (
        parsed.value
        if parsed is not None and parsed.valid
        else None
    )

    route = result.route
    event_type = route
    detail = None

    if route == "new_game":
        event_type = (
            "invitation_created"
            if result.processed
            else "invitation_rejected"
        )

    elif route == "invitation_reply":
        if command == "accept":
            event_type = "invitation_accepted"
        elif command == "decline":
            event_type = "invitation_declined"
        else:
            event_type = "invitation_reply"

    elif route == "game_message":
        if command == "move":
            event_type = (
                "move_accepted"
                if result.processed
                else "move_rejected"
            )
            detail = value
        else:
            event_type = (
                "command_processed"
                if result.processed
                else "command_rejected"
            )
            detail = command

    elif route == "game_help":
        event_type = "help_requested"

    elif route == "game_board":
        event_type = "board_requested"

    elif route == "game_moves":
        event_type = "move_history_requested"

    elif route == "draw_offer":
        event_type = "draw_offered"

    elif route == "draw_declined":
        event_type = "draw_declined"

    elif route == "rematch":
        event_type = "rematch_created"

    elif route == "game_finished":
        if command == "resign":
            event_type = "game_resigned"

        elif command == "accept_draw":
            event_type = "draw_accepted"

        elif command == "move":
            event_type = "game_finished"
            detail = value

        else:
            event_type = "game_finished"

    log_activity(
        event_type,
        game_code=result.game_code,
        actor_email=received_email.sender_email,
        detail=detail,
        db_path=db_path,
    )


def record_delivery_results(
    result,
    deliveries,
    db_path: Path,
) -> None:
    for delivery in deliveries:
        event_type = (
            "email_scheduled"
            if delivery.scheduled
            else "email_sent"
        )

        detail = f"mode={delivery.mode}"

        if delivery.provider_id:
            detail += (
                f" provider={delivery.provider_id}"
            )

        log_activity(
            event_type,
            game_code=result.game_code,
            target_email=delivery.recipient,
            detail=detail,
            db_path=db_path,
        )
