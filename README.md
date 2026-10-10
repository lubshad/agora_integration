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
