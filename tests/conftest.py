"""Put the plugin's scripts/ directory on sys.path so tests can `import superctx`."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
