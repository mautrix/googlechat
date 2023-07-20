from mautrix.util.async_db import UpgradeTable

upgrade_table = UpgradeTable()

from . import (
    v00_latest_revision,
    v02_reactions,
    v03_store_gc_revision,
    v04_store_photo_hash,
    v05_rename_thread_columns,
    v06_space_description,
    v07_puppet_contact_info_set,
    v08_web_app_auth,
    v09_web_app_ua,
    v10_store_microsecond_timestamp,
)
