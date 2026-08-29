#!/bin/bash
set -euo pipefail

cd "$(dirname "$0")"

declare -A ui_files=(
    [ptbuilder.ui]=../ui_ptbuilder.py
    [txbuilder.ui]=../ui_txbuilder.py
    [pxbuilder.ui]=../ui_pxbuilder.py
    [adduni.ui]=../ui_adduni.py
    [addinv.ui]=../ui_addinv.py
    [uniguess.ui]=../ui_uniguess.py
)

for ui in "${!ui_files[@]}"; do
    out=${ui_files[$ui]}
    pyuic6 "$ui" > "$out"
    # pyuic6 generates `from PyQt6 import ...`; use qtpy instead so the app
    # stays usable with either pyqt5 or pyqt6.
    sed -i.bak -E 's/^from PyQt6 import/from qtpy import/' "$out"
    rm -f "$out.bak"
done
