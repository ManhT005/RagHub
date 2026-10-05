import gzip
import hashlib
import os
import tempfile
from pathlib import Path

import tiktoken

# Bundle the encoding so workers can start without a runtime internet connection.
_CACHE_KEY = "9b5ad71b2ce5302211f9c61530b329a4922fc6a4"
_EXPECTED_HASH = "223921b76ee99bde995b7ff738513eef100fb51d18c93597a113bcffe865b2a7"
_CACHE_DIR = Path(tempfile.gettempdir()) / "raghub-token-cache"
_CACHE_DIR.mkdir(parents=True, exist_ok=True)
_CACHE_FILE = _CACHE_DIR / _CACHE_KEY
if not _CACHE_FILE.exists():
    payload = gzip.decompress(
        Path(__file__).with_name("token_cache").joinpath(f"{_CACHE_KEY}.gz").read_bytes()
    )
    if hashlib.sha256(payload).hexdigest() != _EXPECTED_HASH:
        raise RuntimeError("Bundled tokenizer data is corrupt.")
    with tempfile.NamedTemporaryFile(dir=_CACHE_DIR, delete=False) as temporary:
        temporary.write(payload)
        temporary_path = temporary.name
    os.replace(temporary_path, _CACHE_FILE)
os.environ["TIKTOKEN_CACHE_DIR"] = str(_CACHE_DIR)
ENCODING = tiktoken.get_encoding("cl100k_base")
