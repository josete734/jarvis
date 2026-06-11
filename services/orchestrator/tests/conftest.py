"""Hace importables los módulos del orquestador (security_core, ssrf_guard)
desde los tests, sin instalar el paquete."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
