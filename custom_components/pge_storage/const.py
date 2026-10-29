"""Constants for the read-only energy ledger."""

from hashlib import sha256
from pathlib import Path

DOMAIN = "pge_storage"
VERSION = "0.16.1"
TIME_ZONE = "Europe/Warsaw"
DEFAULT_MAX_AGE_HOURS = 24
STORAGE_VERSION = 2
SIGNAL_LEDGER_UPDATED = "pge_storage_updated"
# The URL changes with the actual frontend bytes as well as the release number.
_FRONTEND = Path(__file__).parent / "frontend"
_FRONTEND_HASH = sha256(
    b"".join(path.read_bytes() for path in sorted(_FRONTEND.glob("*.js")))
).hexdigest()[:12]
CARD_URL = f"/pge_storage/pge-storage-card.js?v={VERSION}&build={_FRONTEND_HASH}"
