from mautrix.util.async_db import UpgradeTable

upgrade_table = UpgradeTable()

from . import v01_initial_revision, v02_reactions, v03_store_gc_revision
