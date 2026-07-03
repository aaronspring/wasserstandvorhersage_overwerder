#!/bin/bash
# SessionStart-Hook: installiert die Python-Abhaengigkeiten (pandas/numpy/
# matplotlib/requests) aus pyproject.toml, damit Tests und die CLIs
# (calibrate.py/forecast.py) in Claude-Code-Web-Sessions sofort laufen.
#
# Voraussetzung: pypi.org und files.pythonhosted.org muessen in der
# Netzwerk-Egress-Policy der Umgebung freigegeben sein (sonst 403 beim Install).
set -euo pipefail

# Nur in der Remote-/Web-Umgebung ausfuehren; lokale Sessions unveraendert.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

echo "[session-start] Installiere Python-Abhaengigkeiten ..."
if command -v uv >/dev/null 2>&1; then
  uv pip install --system -q -e .
else
  python -m pip install --disable-pip-version-check -q -e .
fi

echo "[session-start] Fertig. Installierte Kernpakete:"
python -c "import pandas, numpy, matplotlib, requests; \
print('  pandas', pandas.__version__, '| numpy', numpy.__version__, \
'| matplotlib', matplotlib.__version__, '| requests', requests.__version__)"
