"""Load ``scripts/install.py``, which is not part of the package (plan §2 "Arranque con icono")."""

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "install.py"

_spec = importlib.util.spec_from_file_location("exitmap_install_script", SCRIPT)
install = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(install)
