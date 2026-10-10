from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import Mock, patch

from agora_integration.services import push


class RingPushDeliveryTests(TestCase):
	def _session(self) -> SimpleNamespace:
		return SimpleNamespace(
			name="CALL-1",
			caller="member@sync.test",
			recipient="listener@sync.test",
			mode="video",
			state="Ringing",
			project="sync_dating",
		)

	def test_deliver_builds_data_only_android_and_ios_category(self) -> None:
		messaging = Mock()
		with patch.object(push.frappe.db, "get_value", return_value="Member"):
			push._deliver(messaging, "firebase-app", self._session(), ["tok1", "tok2"])

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

	def test_enqueue_requires_recipient(self) -> None:
		with patch.object(push.frappe, "enqueue") as enqueue:
			push.enqueue_ring_push(SimpleNamespace(name="CALL-1", recipient=None))
		enqueue.assert_not_called()


class RingPushSendTests(TestCase):
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
		settings = Mock()
		settings.get.return_value = True
		cache = Mock(**{"get_value.return_value": None})
		with (
			patch.object(push.frappe, "get_single", return_value=settings),
			patch.object(push.frappe, "cache", new=cache),
			patch.object(
				push.frappe.db,
				"get_value",
				return_value=SimpleNamespace(recipient="r@x", project="sync_dating"),
			),
			patch.object(push, "_recipient_tokens", return_value=[]),
			patch.object(push, "_deliver") as deliver,
		):
			push.send_ring_push("CALL-1")
		deliver.assert_not_called()
