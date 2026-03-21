from __future__ import annotations
"""
WhatsApp Service — Twilio WhatsApp integration for COD confirmation.
Falls back to mock if credentials not configured.
"""
import os
import logging
from typing import Dict

logger = logging.getLogger(__name__)


def send_whatsapp_confirmation(
    to_phone: str,
    order_id: str,
    order_value: float,
    rto_score: float,
) -> Dict:
    """
    Send a WhatsApp confirmation message for high-risk COD orders.
    Uses Twilio if credentials are set, otherwise returns a mock response.
    """
    account_sid = os.getenv("TWILIO_ACCOUNT_SID", "")
    auth_token = os.getenv("TWILIO_AUTH_TOKEN", "")
    from_whatsapp = os.getenv("TWILIO_WHATSAPP_FROM", "")

    if account_sid and auth_token and from_whatsapp:
        try:
            from twilio.rest import Client  # type: ignore
            client = Client(account_sid, auth_token)
            message_body = (
                f"🚚 *ZenRTO — Order Confirmation*\n\n"
                f"Order ID: {order_id}\n"
                f"Amount: ₹{order_value:,.2f} (Cash on Delivery)\n\n"
                f"Please reply *YES* to confirm your order or *NO* to cancel.\n"
                f"This helps us ensure smooth delivery for you!"
            )
            msg = client.messages.create(
                body=message_body,
                from_=f"whatsapp:{from_whatsapp}",
                to=f"whatsapp:{to_phone}",
            )
            logger.info(f"WhatsApp sent to {to_phone}: SID={msg.sid}")
            return {"success": True, "sid": msg.sid, "source": "twilio"}
        except ImportError:
            logger.warning("twilio package not installed. pip install twilio")
        except Exception as e:
            logger.warning(f"Twilio WhatsApp failed: {e}")
            return {"success": False, "error": str(e), "source": "twilio"}

    # Mock response when credentials not configured
    logger.info(f"[MOCK] WhatsApp confirmation for order {order_id} to {to_phone}")
    return {
        "success": True,
        "sid": f"MOCK_SID_{order_id}",
        "source": "mock",
        "message": f"Mock WhatsApp confirmation sent to {to_phone}",
    }
