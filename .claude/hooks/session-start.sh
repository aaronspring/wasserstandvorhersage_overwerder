#!/bin/bash
# SessionStart-Hook: installiert die Python-Abhaengigkeiten (pandas/numpy/
# matplotlib/requests) aus requirements.txt, damit Tests und die CLIs
# (calibrate.py/forecast.py) in Claude-Code-Web-Sessions sofort laufen.
#
# Voraussetzung: pypi.org und files.pythonhosted.org muessen in der
# Netzwerk-Egress-Policy der Umgebung freigegeben sein (sonst 403 von pip).
set -euo pipefail

# Nur in der Remote-/Web-Umgebung ausfuehren; lokale Sessions unveraendert.
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "${CLAUDE_PROJECT_DIR:-.}"

echo "[session-start] Installiere Python-Abhaengigkeiten ..."
python -m pip install --disable-pip-version-check -q -r requirements.txt

echo "[session-start] Fertig. Installierte Kernpakete:"
python -c "import pandas, numpy, matplotlib, requests; \
print('  pandas', pandas.__version__, '| numpy', numpy.__version__, \
'| matplotlib', matplotlib.__version__, '| requests', requests.__version__)"
