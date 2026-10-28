#!/usr/bin/env bash
# ==============================================================================
# Live Integration Test: `colab uv run` (CPU runtime only - NO GPU, NO High-RAM)
# ==============================================================================
# Verifies end-to-end execution of uv workflows against a real Colab backend.
# Allocates a standard CPU VM only to avoid consuming GPU quota or high compute costs.
#
# Run with: uv run bash integration/repro_uv_run/test.sh

# Do not set -e so we can capture output, verify failures, and clean up safely.
set -u

# ---------- Auth detection ----------------------------------------------------
if [ -f "$HOME/.config/colab-cli/token.json" ]; then
    AUTH_FLAGS="--auth=oauth2"
elif command -v gcloud > /dev/null && gcloud auth application-default print-access-token > /dev/null 2>&1; then
    ADC_TOKEN=$(gcloud auth application-default print-access-token 2>/dev/null)
    ADC_SCOPES=$(curl -s "https://www.googleapis.com/oauth2/v3/tokeninfo?access_token=$ADC_TOKEN" | python3 -c "import json,sys; print(json.load(sys.stdin).get('scope',''))" 2>/dev/null)
    if echo "$ADC_SCOPES" | grep -q "colaboratory" && echo "$ADC_SCOPES" | grep -q "userinfo.email"; then
        AUTH_FLAGS="--auth=adc"
    else
        echo "Error: ADC token lacks required scopes (colaboratory + userinfo.email)."
        exit 1
    fi
else
    echo "Error: No usable auth provider found. Run 'colab sessions' to authenticate."
    exit 1
fi
echo "[*] Using $AUTH_FLAGS"

# ---------- Test environment -------------------------------------------------
TMP_DIR=$(mktemp -d)
PROJECT_DIR="$TMP_DIR/test_project"
SESSION_NAME="repro-uv-$(date +%s)"

mkdir -p "$PROJECT_DIR"

cleanup() {
    echo ""
    echo "[*] Cleaning up session and temporary files..."
    uv run colab $AUTH_FLAGS stop -s "$SESSION_NAME" 2>/dev/null || true
    rm -rf "$TMP_DIR"
    echo "[*] Cleanup complete."
}
trap cleanup EXIT INT TERM

cd "$PROJECT_DIR"

# ---------- Setup local workspace --------------------------------------------
# 1. Generate ignore file
uv run colab $AUTH_FLAGS uv --gitignore

if [ ! -f .colabignore ]; then
    echo "[FAILURE] .colabignore was not created by 'colab uv --gitignore'"
    exit 1
fi
echo "[PASS] .colabignore created successfully."

# 2. Write test scripts
cat << 'PYEOF' > main.py
import sys
print(f"Colab VM execution OK! Python: {sys.version.split()[0]}")
PYEOF

cat << 'TXTEOF' > file_to_delete.txt
Temporary file that should be removed during mirror sync.
TXTEOF

# ---------- Ensure uv is installed on the remote VM --------------------------
echo "[*] Ensuring remote CPU session '$SESSION_NAME' is provisioned and has uv installed..."
# Provision CPU session explicitly (no GPU, no highmem)
uv run colab $AUTH_FLAGS new -s "$SESSION_NAME"

# Install uv on the remote VM so `uv run` can execute
echo "import shutil, subprocess; subprocess.run('curl -LsSf https://astral.sh/uv/install.sh | sh', shell=True)" | \
    uv run colab $AUTH_FLAGS exec -s "$SESSION_NAME"

# ---------- Phase 1: colab uv run with --keep --------------------------------
echo "[*] Phase 1: Running 'colab uv run' with --keep on CPU session..."
OUTPUT1=$(uv run colab $AUTH_FLAGS uv run -s "$SESSION_NAME" --keep --no-mount-drive --no-sync-back python main.py 2>&1)
RC1=$?
echo "$OUTPUT1"

if [ $RC1 -ne 0 ]; then
    echo "[FAILURE] 'colab uv run' exited with code $RC1"
    exit 1
fi

if ! echo "$OUTPUT1" | grep -q "Colab VM execution OK"; then
    echo "[FAILURE] Expected execution output not found in Phase 1."
    exit 1
fi
echo "[PASS] Phase 1: Script executed successfully via uv on Colab VM."

# Verify session is still alive because of --keep
SESSIONS_KEEP=$(uv run colab $AUTH_FLAGS sessions 2>&1)
if ! echo "$SESSIONS_KEEP" | grep -q "$SESSION_NAME"; then
    echo "[FAILURE] Expected session '$SESSION_NAME' to remain active with --keep."
    exit 1
fi
echo "[PASS] Session remained active as requested by --keep."

# ---------- Phase 2: Mirror sync verification & teardown ---------------------
echo "[*] Phase 2: Testing mirror sync (--delete) and auto-teardown..."
rm -f file_to_delete.txt

cat << 'PYEOF' > verify_mirror.py
import os, sys
if os.path.exists("file_to_delete.txt"):
    print("FAIL: file_to_delete.txt still exists on destination! Mirror sync --delete failed.")
    sys.exit(1)
print("PASS: file_to_delete.txt successfully deleted on remote destination.")

with open("synced_back_result.txt", "w") as f:
    f.write("Successfully generated on remote VM!\n")
PYEOF

# Run on kept session with --sync-back, omitting --keep to trigger default teardown
OUTPUT2=$(uv run colab $AUTH_FLAGS uv run -s "$SESSION_NAME" --sync-back --no-mount-drive python verify_mirror.py 2>&1)
RC2=$?
echo "$OUTPUT2"

if [ $RC2 -ne 0 ]; then
    echo "[FAILURE] 'colab uv run' exited with code $RC2 during Phase 2."
    exit 1
fi

if ! echo "$OUTPUT2" | grep -q "file_to_delete.txt successfully deleted"; then
    echo "[FAILURE] Mirror sync (--delete) did not remove deleted file."
    exit 1
fi
echo "[PASS] Mirror sync (--delete) verified."

if [ ! -f synced_back_result.txt ]; then
    echo "[FAILURE] --sync-back did not retrieve synced_back_result.txt to local directory."
    exit 1
fi
echo "[PASS] --sync-back successfully transferred artifacts to local directory."

# Verify session was stopped automatically
SESSIONS_AFTER=$(uv run colab $AUTH_FLAGS sessions 2>&1)
echo "$SESSIONS_AFTER"
if echo "$SESSIONS_AFTER" | grep -q "$SESSION_NAME"; then
    echo "[FAILURE] Session was not torn down after execution without --keep."
    exit 1
fi
echo "[PASS] Auto-teardown verified: no active sessions remain."

echo ""
echo "======================================================================"
echo "[SUCCESS] All live integration tests for 'colab uv run' passed cleanly."
echo "======================================================================"
