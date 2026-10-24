"""Paymob: Intention API + Unified Checkout (Egypt, EGP) and HMAC verification."""
import hashlib
import hmac
import time

import httpx

from . import config


class PaymentError(Exception):
    pass


# Order matters: Paymob concatenates these transaction fields (sorted lexicographically) before HMAC-SHA512.
HMAC_FIELDS = [
    "amount_cents", "created_at", "currency", "error_occured", "has_parent_transaction", "id",
    "integration_id", "is_3d_secure", "is_auth", "is_capture", "is_refunded", "is_standalone_payment",
    "is_voided", "order.id", "owner", "pending", "source_data.pan", "source_data.sub_type",
    "source_data.type", "success",
]


def configured() -> bool:
    return all([config.PAYMOB_SECRET_KEY, config.PAYMOB_PUBLIC_KEY, config.PAYMOB_INTEGRATION_ID,
                config.PAYMOB_HMAC_SECRET])


def _dig(obj, path):
    for key in path.split("."):
        obj = obj.get(key) if isinstance(obj, dict) else None
    return obj


def _s(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    return "" if v is None else str(v)


def _sign(message: str) -> str:
    return hmac.new(config.PAYMOB_HMAC_SECRET.encode(), message.encode(), hashlib.sha512).hexdigest()


def _matches(message: str, received: str) -> bool:
    if not config.PAYMOB_HMAC_SECRET or not received:
        return False
    return hmac.compare_digest(_sign(message), received.lower())


def verify_transaction(obj: dict, received: str) -> bool:
    """POST callback: body {"type": "TRANSACTION", "obj": {...}}, hmac in query string."""
    return _matches("".join(_s(_dig(obj, f)) for f in HMAC_FIELDS), received)


def verify_redirect(params: dict) -> bool:
    """GET redirect: flat query params; 'order.id' is sent as 'order'."""
    return _matches("".join(params.get("order" if f == "order.id" else f, "") for f in HMAC_FIELDS),
                    params.get("hmac", ""))


def outcome(success, pending) -> str:
    if _s(pending) == "true":
        return "pending"
    return "paid" if _s(success) == "true" else "failed"


def analysis_id_from_reference(ref: str | None) -> str | None:
    return ref.rsplit("-", 1)[0] if ref and "-" in ref else None


def create_intention(analysis_id: str) -> dict:
    if not configured():
        raise PaymentError("Paymob keys are not configured")
    amount_cents = config.PREMIUM_PRICE_EGP * 100
    callback = f"{config.PUBLIC_BACKEND_URL}/api/payments/paymob/callback"
    body = {
        "amount": amount_cents,
        "currency": "EGP",
        "payment_methods": [int(config.PAYMOB_INTEGRATION_ID)],
        "items": [{"name": "Premium plan", "amount": amount_cents, "description": "Full career plan", "quantity": 1}],
        # Paymob requires billing data; we have no user accounts, so placeholders.
        "billing_data": {"first_name": "Career", "last_name": "Student", "email": "student@example.com",
                         "phone_number": "+201000000000", "apartment": "NA", "street": "NA", "building": "NA",
                         "floor": "NA", "city": "Cairo", "state": "Cairo", "country": "EG"},
        "special_reference": f"{analysis_id}-{int(time.time())}",  # must be unique per intention
        "notification_url": callback,
        "redirection_url": callback,
    }
    try:
        r = httpx.post(f"{config.PAYMOB_BASE_URL}/v1/intention/", json=body, timeout=20,
                       headers={"Authorization": f"Token {config.PAYMOB_SECRET_KEY}"})
    except httpx.HTTPError as e:
        raise PaymentError(f"Paymob unreachable: {e}") from e
    if r.status_code >= 400:
        raise PaymentError(f"Paymob error {r.status_code}: {r.text[:300]}")
    secret = r.json()["client_secret"]
    return {
        "checkout_url": f"{config.PAYMOB_BASE_URL}/unifiedcheckout/?publicKey={config.PAYMOB_PUBLIC_KEY}"
                        f"&clientSecret={secret}",
        "amount_egp": config.PREMIUM_PRICE_EGP,
        "client_secret": secret,
        "public_key": config.PAYMOB_PUBLIC_KEY,
    }
