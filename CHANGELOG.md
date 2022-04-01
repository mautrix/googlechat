# v0.3.2 (unreleased)

* Added option to use [MSC2246] async media uploads.
* Added support for syncing read state from Google Chat after backfilling.
* Updated user avatar sync to store hashes and check them before updating
  avatar on Matrix (thanks to [@kpfleming] in [#66]).
  * Usually avatar URLs are stable, but it seems that they aren't in some cases.
    This change should prevent unnecessary avatar change events on Matrix.
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
