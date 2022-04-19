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
