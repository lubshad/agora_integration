from unittest import TestCase
from unittest.mock import Mock, patch

from agora_integration.services import apns


def _settings(**overrides) -> Mock:
	settings = Mock()
	settings.get_password.return_value = "private-key"
	settings.apns_key_id = "ABC123"
	settings.apns_team_id = "TEAM123"
	settings.apns_voip_bundle_id = "com.sync.app"
	settings.app_identifier = ""
	settings.apns_use_sandbox = False
	for key, value in overrides.items():
		setattr(settings, key, value)
	return settings


class ApnsVoipTests(TestCase):
	def test_voip_topic_requires_explicit_bundle_id(self) -> None:
		settings = _settings(apns_voip_bundle_id="", app_identifier="com.sync.app")
		self.assertEqual(apns.voip_topic(settings), "")

	def test_is_configured_requires_key_and_topic(self) -> None:
		self.assertTrue(apns.is_configured(_settings()))
		self.assertFalse(apns.is_configured(_settings(apns_team_id="")))

	def test_payload_includes_callkit_fields(self) -> None:
		payload = apns.build_payload(call_id="CALL-1", name="Sam", mode="video")
		self.assertEqual(payload["id"], "CALL-1")
		self.assertEqual(payload["nameCaller"], "Sam")
		self.assertTrue(payload["isVideo"])
		self.assertEqual(payload["action"], "ring")
		self.assertEqual(payload["handle"], "")
		self.assertIn("aps", payload)

	def test_payload_marks_audio_and_handle(self) -> None:
		payload = apns.build_payload(call_id="CALL-2", name="Sam", mode="audio", handle="u@x", action="end")
		self.assertFalse(payload["isVideo"])
		self.assertEqual(payload["handle"], "u@x")
		self.assertEqual(payload["action"], "end")

	def test_send_posts_voip_and_flags_dead_tokens(self) -> None:
		settings = _settings()
		client = Mock()
		client.post.side_effect = [Mock(status_code=200), Mock(status_code=410)]
		with patch.object(apns, "_auth_token", return_value="jwt-token"):
			dead = apns.send_voip_push(["t1", "t2"], {"id": "CALL-1"}, settings=settings, client=client)
		self.assertEqual(dead, ["t2"])
		first = client.post.call_args_list[0]
		self.assertTrue(first.args[0].startswith("https://api.push.apple.com/3/device/"))
		self.assertEqual(first.kwargs["headers"]["apns-topic"], "com.sync.app.voip")
		self.assertEqual(first.kwargs["headers"]["apns-push-type"], "voip")
		self.assertEqual(first.kwargs["headers"]["apns-priority"], "10")

	def test_send_uses_sandbox_when_configured(self) -> None:
		settings = _settings(apns_use_sandbox=True)
		client = Mock()
		client.post.return_value = Mock(status_code=200)
		with patch.object(apns, "_auth_token", return_value="jwt-token"):
			apns.send_voip_push(["t1"], {"id": "CALL-1"}, settings=settings, client=client)
		self.assertTrue(
			client.post.call_args.args[0].startswith("https://api.development.push.apple.com/3/device/")
		)

	def test_send_is_noop_when_unconfigured(self) -> None:
		client = Mock()
		dead = apns.send_voip_push(
			["t1"], {"id": "CALL-1"}, settings=_settings(apns_key_id=""), client=client
		)
		self.assertEqual(dead, [])
		client.post.assert_not_called()
