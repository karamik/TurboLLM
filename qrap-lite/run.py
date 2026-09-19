#QRAP_LITE_RUN_V1
#!/usr/bin/env python3
"""qrap-lite entry point."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from qrap_lite.server import main  # noqa: E402

if __name__ == "__main__":
    main()
