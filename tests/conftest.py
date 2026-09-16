import sys
from pathlib import Path

# Permite `from python_pipeline import ...` sin instalar el paquete,
# insertando la raiz del repo (flujosscript/) en sys.path.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
