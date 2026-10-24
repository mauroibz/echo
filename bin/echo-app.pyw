"""Windows launcher: runs Echo from this source tree with the clone's environment.

pythonw.exe runs it for the Start Menu entry and "Open with" (no console window); python.exe runs
it for the echo-app command in a terminal.
"""

import os
import sys

root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
src = os.path.join(root, "src")
sys.path.insert(0, src)
os.environ["PYTHONPATH"] = src  # for the recorder and transcriber processes Echo starts

from echo_app.cli import main  # noqa: E402

sys.exit(main())
