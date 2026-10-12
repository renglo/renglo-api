#!/bin/bash
# Create the API virtualenv and install this workspace's Python packages
# from the local checkouts. Public libraries come from PyPI.
#
# A machine pip.conf left behind by `aws codeartifact login` must not be
# used here. Those tokens do not install the clones a developer is editing,
# and an expired token makes `pip install -e .` fail before anything is
# installed.
set -euo pipefail

cd "$(dirname "$0")"

PYPI_INDEX="https://pypi.org/simple"
VENV="${RENGLO_API_VENV:-venv}"
ROOT="$(cd ../.. && pwd)"

if [ ! -d "$VENV" ]; then
    echo "Creating virtual environment..."
    python3.12 -m venv "$VENV"
fi

# PIP_CONFIG_FILE replaces the usual config search, so ~/.config/pip/pip.conf
# (CodeArtifact) is not read while this venv is active.
cat > "$VENV/pip.conf" <<EOF
[global]
index-url = ${PYPI_INDEX}
EOF

ACTIVATE="$VENV/bin/activate"
MARKER="# renglo-api: ignore machine CodeArtifact pip config"
if ! grep -qF "$MARKER" "$ACTIVATE"; then
    cat >> "$ACTIVATE" <<'EOF'

# renglo-api: ignore machine CodeArtifact pip config
export PIP_CONFIG_FILE="$VIRTUAL_ENV/pip.conf"
EOF
fi

# shellcheck disable=SC1091
source "$VENV/bin/activate"

echo "Installing local checkouts. Public dependencies come from PyPI."
pip install --upgrade pip
pip install --index-url "$PYPI_INDEX" -r requirements.txt
pip install --index-url "$PYPI_INDEX" -e .

# elements before ols before scenebreakdown: later packages depend on earlier ones.
preferred=(
    data
    schd
    pes
    claw
    props
    breakdown
    gmail
    whatsapp
    dumbo
    lgx
    elements
    ols
    scenebreakdown
)

install_editable() {
    local path="$1"
    if [ ! -f "$path/pyproject.toml" ]; then
        return 0
    fi
    echo "Installing $path"
    pip install --index-url "$PYPI_INDEX" -e "$path"
}

seen=" "
for name in "${preferred[@]}"; do
    install_editable "$ROOT/extensions/$name/package"
    seen="$seen$name "
done

for path in "$ROOT"/extensions/*/package; do
    [ -d "$path" ] || continue
    name="$(basename "$(dirname "$path")")"
    case "$seen" in
        *" $name "*) continue ;;
    esac
    install_editable "$path"
done

# Tenant white-label pack (import wl), when the checkout has a pyproject.toml.
for path in "$ROOT"/dev/*-wl; do
    [ -d "$path" ] || continue
    install_editable "$path"
done

echo ""
echo "Setup complete. Local packages are editable installs in $VENV."
echo "Activate it with:"
echo "  source $VENV/bin/activate"
echo ""
echo "Then run the API with:"
echo "  source run.sh"
