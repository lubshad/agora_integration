from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from agora_integration.services import push


def _session(state: str = "Ringing") -> SimpleNamespace:
	return SimpleNamespace(
		name="CALL-1",
		caller="member@sync.test",
		recipient="listener@sync.test",
		mode="video",
		state=state,
		project="sync_dating",
	)


class RingPushDeliveryTests(TestCase):
	def test_deliver_builds_data_only_android_and_ios_category(self) -> None:
		messaging = Mock()
		with patch.object(push.frappe.db, "get_value", return_value="Member"):
			push._deliver(messaging, "firebase-app", _session(), ["tok1", "tok2"])

		kwargs = messaging.MulticastMessage.call_args.kwargs
		self.assertEqual(kwargs["tokens"], ["tok1", "tok2"])
		self.assertEqual(kwargs["data"]["type"], "incoming_call")
		self.assertEqual(kwargs["data"]["name"], "Member")
		self.assertEqual(kwargs["data"]["mode"], "video")
		self.assertEqual(kwargs["data"]["project"], "sync_dating")
		# Android is data-only (no notification block) with high priority.
		self.assertNotIn("notification", kwargs)
		self.assertEqual(messaging.AndroidConfig.call_args.kwargs["priority"], "high")
		self.assertEqual(messaging.Aps.call_args.kwargs["category"], "agora_call")
		messaging.send_each_for_multicast.assert_called_once()
		self.assertEqual(messaging.send_each_for_multicast.call_args.kwargs["app"], "firebase-app")

	def test_deliver_uses_the_ended_event_for_dismissals(self) -> None:
		messaging = Mock()
		with patch.object(push.frappe.db, "get_value", return_value="Member"):
			push._deliver(messaging, "firebase-app", _session("Ended"), ["tok1"], event="call_ended")
		self.assertEqual(messaging.MulticastMessage.call_args.kwargs["data"]["type"], "call_ended")

	def test_deliver_voip_disables_dead_tokens(self) -> None:
		rows = [
			SimpleNamespace(name="DEV-1", voip_token="v1"),
			SimpleNamespace(name="DEV-2", voip_token="v2"),
		]
		with (
			patch.object(push.frappe.db, "get_value", return_value="Member"),
			patch("agora_integration.services.apns.send_voip_push", return_value=["v2"]) as send,
			patch.object(push.frappe.db, "set_value") as set_value,
		):
			push._deliver_voip(_session(), rows, "ring")

		payload = send.call_args.args[1]
		self.assertEqual(payload["id"], "CALL-1")
		self.assertEqual(payload["action"], "ring")
		self.assertTrue(payload["isVideo"])
		set_value.assert_called_once_with(
			push.VOIP_REGISTRATION_DOCTYPE, "DEV-2", "voip_enabled", 0, update_modified=False
		)


class RingPushEnqueueTests(TestCase):
	def test_enqueue_targets_worker_after_commit(self) -> None:
		call = SimpleNamespace(name="CALL-1", recipient="r@x")
		with patch.object(push.frappe, "enqueue") as enqueue:
			push.enqueue_ring_push(call)
		enqueue.assert_called_once()
		args, kwargs = enqueue.call_args
		self.assertEqual(args[0], "agora_integration.services.push.send_ring_push")
		self.assertTrue(kwargs["enqueue_after_commit"])
		self.assertEqual(kwargs["call"], "CALL-1")

	def test_enqueue_dismiss_targets_worker_after_commit(self) -> None:
		call = SimpleNamespace(name="CALL-1", recipient="r@x")
		with patch.object(push.frappe, "enqueue") as enqueue:
			push.enqueue_call_dismiss(call)
		args, kwargs = enqueue.call_args
		self.assertEqual(args[0], "agora_integration.services.push.send_call_dismiss")
		self.assertTrue(kwargs["enqueue_after_commit"])

	def test_enqueue_requires_recipient(self) -> None:
		with patch.object(push.frappe, "enqueue") as enqueue:
			push.enqueue_ring_push(SimpleNamespace(name="CALL-1", recipient=None))
		enqueue.assert_not_called()


class RingPushSendTests(TestCase):
	def _settings(self) -> Mock:
		settings = Mock()
		settings.get.return_value = True
		return settings

	def test_send_skips_when_push_disabled(self) -> None:
		settings = Mock()
		settings.get.return_value = False
		with (
			patch.object(push.frappe, "get_single", return_value=settings),
			patch.object(push, "_deliver") as deliver,
		):
			push.send_ring_push("CALL-1")
		deliver.assert_not_called()

	def test_send_skips_without_tokens(self) -> None:
		cache = Mock(**{"get_value.return_value": None})
		with (
			patch.object(push.frappe, "get_single", return_value=self._settings()),
			patch.object(push.frappe, "cache", new=cache),
			patch.object(
				push.frappe.db,
				"get_value",
				return_value=SimpleNamespace(recipient="r@x", project="sync_dating"),
			),
			patch.object(push, "_recipient_tokens", return_value=[]),
			patch.object(push, "_recipient_voip", return_value=[]),
			patch.object(push, "_deliver") as deliver,
		):
			push.send_ring_push("CALL-1")
		deliver.assert_not_called()

	def test_send_rings_ios_voip_and_android_fcm(self) -> None:
		cache = Mock(**{"get_value.return_value": None})
		voip_rows = [SimpleNamespace(name="DEV-1", voip_token="v1")]
		session = SimpleNamespace(
			name="CALL-1",
			caller="c@x",
			recipient="r@x",
			mode="audio",
			state="Ringing",
			project="sync_dating",
		)
		with (
			patch.object(push.frappe, "get_single", return_value=self._settings()),
			patch.object(push.frappe, "cache", new=cache),
			patch.object(push.frappe.db, "get_value", return_value=session),
			patch.object(push, "_recipient_tokens", return_value=["android-token"]),
			patch.object(push, "_recipient_voip", return_value=voip_rows),
			patch.object(push, "_deliver_voip") as deliver_voip,
			patch.object(push, "_deliver") as deliver,
			patch("flutter_utils.firebase.get_firebase_app", return_value="firebase-app"),
		):
			push.send_ring_push("CALL-1")
		deliver_voip.assert_called_once()
		self.assertEqual(deliver_voip.call_args.args[2], "ring")
		deliver.assert_called_once()
		self.assertEqual(deliver.call_args.kwargs["event"], "incoming_call")
		cache.set_value.assert_called_once()

	def test_dismiss_sends_end_action(self) -> None:
		cache = Mock(**{"get_value.return_value": None})
		voip_rows = [SimpleNamespace(name="DEV-1", voip_token="v1")]
		session = SimpleNamespace(
			name="CALL-1",
			caller="c@x",
			recipient="r@x",
			mode="audio",
			state="Ended",
			project="sync_dating",
		)
		with (
			patch.object(push.frappe, "get_single", return_value=self._settings()),
			patch.object(push.frappe, "cache", new=cache),
			patch.object(push.frappe.db, "get_value", return_value=session),
			patch.object(push, "_recipient_tokens", return_value=[]),
			patch.object(push, "_recipient_voip", return_value=voip_rows),
			patch.object(push, "_deliver_voip") as deliver_voip,
		):
			push.send_call_dismiss("CALL-1")
		self.assertEqual(deliver_voip.call_args.args[2], "end")
