"""Apple Push Notification service (APNs) VoIP delivery for CallKit.

Firebase cannot send VoIP pushes, so callers fall back to sending them directly
to APNs using a token-based auth key (.p8). The payload matches the
``flutter_callkit_incoming`` plugin's expected shape: the call fields sit at the
top level (``id`` / ``nameCaller`` / ``handle`` / ``isVideo``) alongside ``aps``.
"""

from __future__ import annotations

import json
import time
from typing import Any

import frappe

APNS_PRODUCTION_HOST = "https://api.push.apple.com"
APNS_SANDBOX_HOST = "https://api.development.push.apple.com"
VOIP_PUSH_TTL_SECONDS = 45


def _settings() -> Any:
	return frappe.get_single("Agora Settings")


def voip_topic(settings: Any | None = None) -> str:
	settings = settings or _settings()
	bundle = str(settings.apns_voip_bundle_id or "").strip()
	return f"{bundle}.voip" if bundle else ""


def is_configured(settings: Any | None = None) -> bool:
	"""True when the APNs key, team, and topic are all present."""
	settings = settings or _settings()
	try:
		key = settings.get_password("apns_private_key")
	except Exception:
		key = None
	return bool(
		key
		and str(settings.apns_key_id or "").strip()
		and str(settings.apns_team_id or "").strip()
		and voip_topic(settings)
	)


def _auth_token(settings: Any) -> str:
	import jwt

	return jwt.encode(
		{"iss": str(settings.apns_team_id).strip(), "iat": int(time.time())},
		settings.get_password("apns_private_key"),
		algorithm="ES256",
		headers={"kid": str(settings.apns_key_id).strip()},
	)


def build_payload(
	*,
	call_id: str,
	name: str,
	mode: str,
	handle: str = "",
	action: str = "ring",
) -> dict[str, Any]:
	"""Build the VoIP payload the CallKit plugin consumes."""
	return {
		"aps": {
			"alert": {"title": "Incoming call", "body": name or "Someone"},
			"content-available": 1,
		},
		"id": str(call_id),
		"nameCaller": name or "Someone",
		"handle": handle or "",
		"isVideo": mode == "video",
		"action": action,
	}


def send_voip_push(
	tokens: list[str],
	payload: dict[str, Any],
	*,
	settings: Any | None = None,
	client: Any | None = None,
) -> list[str]:
	"""Send [payload] to each VoIP [token]; return tokens APNs reported as dead.

	Never raises: delivery failures are logged so a call transaction is never
	affected. HTTP 400/410 mean the token is no longer usable and is returned so
	the caller can disable that device.
	"""
	settings = settings or _settings()
	if not tokens or not is_configured(settings):
		return []
	import httpx

	host = APNS_SANDBOX_HOST if settings.apns_use_sandbox else APNS_PRODUCTION_HOST
	headers = {
		"authorization": f"bearer {_auth_token(settings)}",
		"apns-topic": voip_topic(settings),
		"apns-push-type": "voip",
		"apns-priority": "10",
		"apns-expiration": str(int(time.time()) + VOIP_PUSH_TTL_SECONDS),
	}
	body = json.dumps(payload)
	dead: list[str] = []
	own_client = client is None
	client = client or httpx.Client(http2=True, timeout=10)
	try:
		for token in tokens:
			try:
				response = client.post(f"{host}/3/device/{token}", headers=headers, content=body)
			except Exception:
				frappe.log_error(title="agora_integration.apns", message="APNs VoIP delivery failed.")
				continue
			if response.status_code in (400, 410):
				dead.append(token)
			elif response.status_code >= 500:
				frappe.log_error(title="agora_integration.apns", message="APNs VoIP server error.")
	finally:
		if own_client:
			client.close()
	return dead
