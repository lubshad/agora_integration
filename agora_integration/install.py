"""Apply the same app setup to fresh installations as migrated sites."""

from agora_integration.patches.v1_0 import move_user_presence, move_voip_from_flutter_utils


def after_install() -> None:
	move_user_presence.execute()
	move_voip_from_flutter_utils.execute()
