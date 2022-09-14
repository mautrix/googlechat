from mautrix.util.async_db import UpgradeTable

upgrade_table = UpgradeTable()

from . import v00_latest_revision, v02_reactions, v03_store_gc_revision, v04_store_photo_hash
