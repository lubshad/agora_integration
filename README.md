### Agora Integration

Reusable user-to-user audio and video calling powered by Agora

### Installation

You can install this app using the [bench](https://github.com/frappe/bench) CLI:

```bash
cd $PATH_TO_YOUR_BENCH
bench get-app $URL_OF_THIS_REPO --branch version-16
bench install-app agora_integration
```

### Presence and incoming-call push

- `agora_integration.api.set_presence(state)` (POST) records the signed-in user's
  app presence (`Foreground` / `Background` / `Offline`) on `User.agora_presence`,
  with `User.agora_last_seen` used to decay stale reports to `Offline`.
  The staleness window is `Agora Settings.presence_stale_after` (seconds).
- When a call starts ringing, `agora_integration` sends a data-only Android
  (high priority) push plus an iOS alert with the `agora_call` action category,
  but only when the recipient is not `Foreground`. Foreground clients rely on the
  `agora_call_updated` realtime event and show the in-app ring instead.
- Clients register FCM tokens through `flutter_utils`; the push targets tokens
  whose `app` matches the call's `project`.

### iOS PushKit / CallKit

- APNs delivery, configuration, and VoIP registrations belong to this app.
  Configure Team ID, Key ID, private `.p8` key, explicit iOS bundle ID, and sandbox
  mode in **Agora Settings**. These settings are independent of Firebase push.
- Register with POST `agora_integration.api.push_notifications.register_voip_device`
  (`token`, `app`); unregister with POST
  `agora_integration.api.push_notifications.unregister_voip_device` (`token`).
  Both are also exported from `agora_integration.api`.
- Both endpoints require managed-device authentication: `Authorization: token
  <api_key>:<api_secret>` and `Frappe-Authorization-Source: Flutter Device Credential`.
  Registration returns `{"name": "<managed device name>", "active": true}`.
- Tokens are stored in **Agora VoIP Device**, linked to the managed device and
  scoped by application/project. Logout, device-limit revocation, administrator
  disable, and credential deletion deactivate/remove registrations. Recipient
  lookup additionally excludes disabled credentials.
- On upgrade, run `bench --site <site> migrate` with both apps updated. The data
  patch transfers legacy APNs settings (including encrypted key and implicit
  bundle-ID fallback) and device tokens, then clears migrated legacy values.
  Existing Agora values are preserved. Update clients using the old
  `flutter_utils.api.push_notifications.*voip_device` paths to the paths above.
- Ordinary FCM registration stays in Flutter Utils. Call pushes continue to run
  in after-commit background jobs.

### Contributing

This app uses `pre-commit` for code formatting and linting. Please [install pre-commit](https://pre-commit.com/#installation) and enable it for this repository:

```bash
cd apps/agora_integration
pre-commit install
```

Pre-commit is configured to use the following tools for checking and formatting your code:

- ruff
- eslint
- prettier
- pyupgrade

### License

mit
