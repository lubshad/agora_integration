from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from agora_integration.services import notifications


def _call(state: str = "Ringing") -> SimpleNamespace:
	return SimpleNamespace(
		name="CALL-1",
		state=state,
		version=1,
		project="sync_dating",
		deadline=None,
		caller="caller@sync.test",
		recipient="recipient@sync.test",
		mode="audio",
	)


class NotifyPushGateTests(TestCase):
	def _notify(self, presence: str, state: str = "Ringing"):
		with (
			patch.object(notifications.frappe, "publish_realtime") as publish,
			patch.object(notifications, "get_presence", return_value=presence) as get_presence,
			patch.object(notifications, "enqueue_ring_push") as enqueue,
		):
			notifications.notify(_call(state))
		return publish, get_presence, enqueue

	def test_foreground_recipient_skips_push(self) -> None:
		publish, _, enqueue = self._notify("Foreground")
		enqueue.assert_not_called()
		self.assertEqual(publish.call_count, 2)

	def test_background_recipient_pushes(self) -> None:
		_, _, enqueue = self._notify("Background")
		enqueue.assert_called_once()

	def test_offline_recipient_pushes(self) -> None:
		_, _, enqueue = self._notify("Offline")
		enqueue.assert_called_once()

	def test_non_ringing_call_never_pushes(self) -> None:
		_, get_presence, enqueue = self._notify("Background", state="Active")
		enqueue.assert_not_called()
		get_presence.assert_not_called()
