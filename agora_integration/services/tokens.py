"""RTC-only AccessToken2 encoding, following AgoraIO/Tools' Token007 format.

Reference: DynamicKey/AgoraDynamicKey/python3/src/AccessToken2.py and
RtcTokenBuilder2.py. Uses only Python's standard library. No secrets are cached.
"""

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
import zlib
from typing import Any

import frappe
from frappe import _


def _string(value: bytes) -> bytes:
	return struct.pack("<H", len(value)) + value


def build_rtc_token(
	app_id: str,
	certificate: str,
	channel: str,
	uid: int,
	ttl: int,
	issue_time: int | None = None,
	salt: int | None = None,
) -> str:
	"""Encode join and publisher privileges for a nonzero, channel-bound UID."""
	if not all(re.fullmatch(r"[a-fA-F0-9]{32}", value) for value in (app_id, certificate)):
		raise ValueError("Invalid Agora identifiers")
	if not 0 < uid < 2**32 or not 60 <= ttl <= 3600 or not re.fullmatch(r"[a-zA-Z0-9_-]{1,63}", channel):
		raise ValueError("Invalid RTC token parameters")
	issued = issue_time if issue_time is not None else int(time.time())
	nonce = salt if salt is not None else secrets.randbelow(99999999) + 1
	key = hmac.new(struct.pack("<I", issued), certificate.encode(), hashlib.sha256).digest()
	key = hmac.new(struct.pack("<I", nonce), key, hashlib.sha256).digest()
	# One RTC service (type 1), four publisher privileges with relative TTL.
	service = struct.pack("<HH", 1, 4)
	service += b"".join(struct.pack("<HI", privilege, ttl) for privilege in (1, 2, 3, 4))
	service += _string(channel.encode()) + _string(str(uid).encode())
	info = _string(app_id.encode()) + struct.pack("<IIIH", issued, ttl, nonce, 1) + service
	signature = hmac.new(key, info, hashlib.sha256).digest()
	return "007" + base64.b64encode(zlib.compress(_string(signature) + info)).decode()


def get_settings() -> Any:
	settings = frappe.get_single("Agora Settings")
	if not settings.enabled:
		frappe.throw(_("Calling is not configured or is disabled."))
	certificate = settings.get_password("app_certificate", raise_exception=False) or ""
	if not all(re.fullmatch(r"[a-fA-F0-9]{32}", value or "") for value in (settings.app_id, certificate)):
		frappe.throw(_("Ask an administrator to configure Agora credentials."))
	return settings


def issue_token(channel: str, uid: int) -> dict[str, Any]:
	settings = get_settings()
	ttl = int(settings.token_ttl or 600)
	return {
		"app_id": settings.app_id,
		"channel": channel,
		"uid": uid,
		"token": build_rtc_token(
			settings.app_id, settings.get_password("app_certificate"), channel, uid, ttl
		),
		"expires_at": int(time.time()) + ttl,
	}
