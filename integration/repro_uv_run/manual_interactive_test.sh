#!/usr/bin/env bash
# ==============================================================================
# Interactive End-to-End Test for `colab uv run`
# ==============================================================================
# This script is git-excluded and will not be tracked or committed to git.
# Run with: bash integration/manual_uv_e2e_test.sh

set -euo pipefail

TEST_DIR="/tmp/test_colab_uv_$$"
SESSION_NAME="e2e-uv-test-$$"

echo "======================================================================"
echo " Starting Interactive E2E Verification for 'colab uv'"
echo " Workspace: $TEST_DIR"
echo " Session:   $SESSION_NAME"
echo "======================================================================"

mkdir -p "$TEST_DIR"
cd "$TEST_DIR"

cleanup() {
    echo ""
    echo "==> Cleaning up test environment..."
    colab stop -s "$SESSION_NAME" 2>/dev/null || true
    rm -rf "$TEST_DIR"
    echo "==> Done."
}
trap cleanup EXIT INT TERM

# ------------------------------------------------------------------------------
# Phase 1: Test `colab uv --gitignore`
# ------------------------------------------------------------------------------
echo ""
echo "[Phase 1/4] Testing 'colab uv --gitignore' template generation..."
colab uv --gitignore
if [[ -f .colabignore ]]; then
    echo "PASS: .colabignore created successfully:"
    head -n 6 .colabignore
else
    echo "FAIL: .colabignore was not created."
    exit 1
fi

# ------------------------------------------------------------------------------
# Phase 2: Create a minimal uv project
# ------------------------------------------------------------------------------
echo ""
echo "[Phase 2/4] Setting up minimal project with dummy file..."
cat << 'EOF' > main.py
import sys
print(f"Hello from Colab remote VM! Python: {sys.version}")
EOF

cat << 'EOF' > to_delete.txt
This file should be deleted on Colab during the mirror sync test.
EOF

# ------------------------------------------------------------------------------
# Phase 3: Run `colab uv run` with `--keep`
# ------------------------------------------------------------------------------
echo ""
echo "[Phase 3/4] Running 'colab uv run' with --keep..."
echo "(You will be prompted to select a machine and optionally mount Google Drive)"
colab uv run --keep -s "$SESSION_NAME" python main.py

echo ""
echo "Verifying session is alive in 'colab sessions'..."
colab sessions | grep "$SESSION_NAME"

# ------------------------------------------------------------------------------
# Phase 4: Test Mirror Sync (--delete) and Session Reuse on kept session
# ------------------------------------------------------------------------------
echo ""
echo "[Phase 4/4] Testing iterative session reuse and mirror sync (--delete)..."
echo "Deleting local 'to_delete.txt' and creating 'check_mirror.py'..."
rm -f to_delete.txt

cat << 'EOF' > check_mirror.py
import os, sys
if os.path.exists("to_delete.txt"):
    print("FAIL: to_delete.txt still exists on Colab! Mirror sync did not delete it.")
    sys.exit(1)
print("PASS: to_delete.txt was successfully deleted on Colab! Mirror sync verified.")

with open("output_artifact.txt", "w") as f:
    f.write("Generated on Colab VM!\n")
print("Created remote output_artifact.txt")
EOF

echo "Re-running on kept session with --sync-back (without --keep to trigger teardown)..."
colab uv run -s "$SESSION_NAME" --sync-back python check_mirror.py

if [[ -f output_artifact.txt ]]; then
    echo "PASS: output_artifact.txt successfully synced back to local workspace!"
    cat output_artifact.txt
else
    echo "FAIL: output_artifact.txt was not synced back."
    exit 1
fi

echo ""
echo "======================================================================"
echo " ALL INTERACTIVE E2E VERIFICATIONS PASSED!"
echo "======================================================================"

