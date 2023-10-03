# v0.5.1 (2023-10-03)

* Added support for double puppeting with arbitrary `as_token`s.
  See [docs](https://docs.mau.fi/bridges/general/double-puppeting.html#appservice-method-new) for more info.
* Added support for replies.
* Fixed bridge disconnecting for no reason after 14 days of uptime.

# v0.5.0 (2023-06-16)

* Switched to web app API to make authentication work again.
  **This will require all users to relogin.**
* Allowed thread bridging in non-thread-only chats.
* Improved handling of getting logged out remotely.
* Added options to automatically ratchet/delete megolm sessions to minimize
  access to old messages.
* Added option to not set room name/avatar even in encrypted rooms.
* Implemented appservice pinging using MSC2659.
* Updated Docker image to Alpine 3.18.

# v0.4.0 (2022-11-15)

* Added support for bridging room mentions in both directions.
* Updated formatter to insert Matrix displayname into mentions when bridging
  from Google Chat. This ensures that the Matrix user gets mentioned correctly.
* Fixed images from Google Chat not being bridged with full resolution.
* Added SQLite support (thanks to [@durin42] in [#74]).
* Updated Docker image to Alpine 3.16.
* Enabled appservice ephemeral events by default for new installations.
  * Existing bridges can turn it on by enabling `ephemeral_events` and disabling
    `sync_with_custom_puppets` in the config, then regenerating the registration
    file.
* Added options to make encryption more secure.
  * The `encryption` -> `verification_levels` config options can be used to
    make the bridge require encrypted messages to come from cross-signed
    devices, with trust-on-first-use validation of the cross-signing master
    key.
  * The `encryption` -> `require` option can be used to make the bridge ignore
    any unencrypted messages.
  * Key rotation settings can be configured with the `encryption` -> `rotation`
    config.

[@durin42]: https://github.com/durin42
[#74]: https://github.com/mautrix/googlechat/pull/74

# v0.3.3 (2022-06-03)

* Switched to using native Matrix threads for bridging Google Chat threads.
* Removed web login interface and added support for logging in inside Matrix.
  * The provisioning API is still available, but it has moved from `/login/api`
    to `/_matrix/provision/v1`.
* Added error messages and optionally custom status events to detect when
  a message fails to bridge.

# v0.3.2 (2022-04-19)

**N.B.** This release drops support for old homeservers which don't support the
new `/v3` API endpoints. Synapse 1.48+, Dendrite 0.6.5+ and Conduit 0.4.0+ are
supported. Legacy `r0` API support can be temporarily re-enabled with `pip install mautrix==0.16.0`.
However, this option will not be available in future releases.

* Added option to use [MSC2246] async media uploads.
* Added support for syncing read state from Google Chat after backfilling.
* Updated user avatar sync to store hashes and check them before updating
  avatar on Matrix (thanks to [@kpfleming] in [#66]).
  * Usually avatar URLs are stable, but it seems that they aren't in some cases.
    This change should prevent unnecessary avatar change events on Matrix.
* Changed event handling to work synchronously to make sure incoming messages
  are bridged in the correct order.
* Fixed bug where messages being sent while the bridge is reconnecting to
  Google Chat would fail completely.
* Removed unnecessary warning log about `COMPASS` cookies.

[@kpfleming]: https://github.com/kpfleming
[#66]: https://github.com/mautrix/googlechat/pull/66
[MSC2246]: https://github.com/matrix-org/matrix-spec-proposals/pull/2246

# v0.3.1 (2022-03-16)

* Ignored errors getting `COMPASS` cookie as Google appears to have changed
  something.
* Improved attachment bridging support.
  * Drive and YouTube links will be bridged even when they're sent as
    attachments (rather than text messages).
  * Bridging big files uses less memory now
    (only ~1-2x file size rather than 2-4x).
  * Link preview metadata is now included in the Matrix events
    (in a custom field).
* Disabled file logging in Docker image by default.
  * If you want to enable it, set the `filename` in the file log handler to
    a path that is writable, then add `"file"` back to `logging.root.handlers`.
* Formatted all code using [black](https://github.com/psf/black)
  and [isort](https://github.com/PyCQA/isort).

# v0.3.0 (2021-12-18)

Initial stable-ish Google Chat release
