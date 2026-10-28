#!/usr/bin/env fish

# ==============================================================================
# Google Colab A100 Training Orchestrator for Model v1
# ==============================================================================

set -l LOCAL_REPO (pwd)
if test (path basename "$LOCAL_REPO") = "google_colab"
    set LOCAL_REPO (path dirname "$LOCAL_REPO")
end

# 1. Parse Experiment Flag, Model Target & Session Name
set -l FLAG_ARG ""
set -l MODEL_ARG ""
set -l SESSION_ARG ""

if test (count $argv) -ge 1
    set FLAG_ARG "$argv[1]"
end
if test (count $argv) -ge 2
    set MODEL_ARG "$argv[2]"
end
if test (count $argv) -ge 3
    set SESSION_ARG "$argv[3]"
end

set -g FLAG_NAME "$FLAG_ARG"
if test -z "$FLAG_NAME"
    set -l default_flag "encoder"
    if test -f "$LOCAL_REPO/.env"
        set -l env_flag (grep -E "^EXPERIMENT_TAG=" "$LOCAL_REPO/.env" 2>/dev/null | cut -d= -f2 | string trim)
        if test -n "$env_flag"
            set default_flag "$env_flag"
        end
    end
    read -l -P "Enter experiment flag/name [default: $default_flag]: " prompted_flag
    if test -n "$prompted_flag"
        set FLAG_NAME "$prompted_flag"
    else
        set FLAG_NAME "$default_flag"
    end
end

set -g MODEL_TARGET "$MODEL_ARG"
if test -z "$MODEL_TARGET"
    set -l default_model "v1"
    if test -f "$LOCAL_REPO/.env"
        set -l env_model (grep -E "^AE_MODEL_TYPE=" "$LOCAL_REPO/.env" 2>/dev/null | cut -d= -f2 | string trim)
        if test -n "$env_model"
            set default_model "$env_model"
        end
    end
    read -l -P "Enter model folder to run [default: $default_model]: " prompted_model
    if test -n "$prompted_model"
        set MODEL_TARGET "$prompted_model"
    else
        set MODEL_TARGET "$default_model"
    end
end

# Resolve model directory and main.py runner
set -g MODEL_RUNNER_REL ""
set -g MODEL_RUNNER_FULL ""

if test -f "$LOCAL_REPO/aprendizados/mono/$MODEL_TARGET/main.py"
    set MODEL_RUNNER_REL "aprendizados/mono/$MODEL_TARGET/main.py"
    set MODEL_RUNNER_FULL "$LOCAL_REPO/aprendizados/mono/$MODEL_TARGET/main.py"
else if test -f "$LOCAL_REPO/$MODEL_TARGET/main.py"
    set MODEL_RUNNER_REL "$MODEL_TARGET/main.py"
    set MODEL_RUNNER_FULL "$LOCAL_REPO/$MODEL_TARGET/main.py"
else if test -f "$LOCAL_REPO/$MODEL_TARGET"
    set MODEL_RUNNER_REL "$MODEL_TARGET"
    set MODEL_RUNNER_FULL "$LOCAL_REPO/$MODEL_TARGET"
else
    echo "======================================================================"
    echo "FATAL ERROR: Could not find main.py in model target '$MODEL_TARGET'!"
    echo "Checked locations:"
    echo " - $LOCAL_REPO/aprendizados/mono/$MODEL_TARGET/main.py"
    echo " - $LOCAL_REPO/$MODEL_TARGET/main.py"
    echo "======================================================================"
    exit 1
end

set -g SESSION_NAME "colab-$MODEL_TARGET-train"
if test -n "$SESSION_ARG"
    set -g SESSION_NAME "$SESSION_ARG"
end

set -g SESSION_PROVISIONED 0
set -g CLEANUP_DONE 0

# Resolve TAG_NAME from .env if present
set -l env_tag ""
if test -f "$LOCAL_REPO/.env"
    set env_tag (grep -E "^TAG_NAME=" "$LOCAL_REPO/.env" 2>/dev/null | cut -d= -f2 | string trim | string trim -c '"' | string trim -c "'")
end

set -g RUN_BASE_DATE (date "+%Y_%m_%d_%H_%M_%S")
if test -n "$env_tag"
    set -l clean_tag (string trim -l -c _ "$env_tag")
    set -g RUN_TIMESTAMP "$RUN_BASE_DATE"_"$clean_tag"
else
    set -g RUN_TIMESTAMP "$RUN_BASE_DATE"
end
set -g LOCAL_OUT "$LOCAL_REPO/experiments/$FLAG_NAME/$RUN_TIMESTAMP"
mkdir -p "$LOCAL_OUT"

echo "======================================================================"
echo " Google Colab Training Pipeline"
echo " Model Target:    $MODEL_TARGET ($MODEL_RUNNER_REL)"
echo " Experiment Flag: $FLAG_NAME"
echo " Run Version:     $RUN_TIMESTAMP"
echo " Local Output:    $LOCAL_OUT"
echo " Config File:     $LOCAL_REPO/.env"
echo "======================================================================"

# 1. Interactive Hardware Accelerator Selection
echo "Select Hardware Accelerator for the Colab VM:"
echo "----------------------------------------------------------------------------------------"
echo " [GPUs]"
echo "  [1] G4 GPU      (96 GB GDDR7)          - NVIDIA RTX PRO 6000 Blackwell Server Edition"
echo "  [2] A100 GPU    (40 GB / 80 GB HBM2e)  - NVIDIA A100 Tensor Core (High Compute)"
echo "  [3] L4 GPU      (24 GB GDDR6)          - NVIDIA L4 Ada Lovelace"
echo "  [4] T4 GPU      (16 GB GDDR6)          - NVIDIA T4 (Standard budget GPU)"
echo "  [5] H100 GPU    (80 GB HBM3)           - NVIDIA H100 Tensor Core (Google AI Ultra tier)"
echo ""
echo " [TPUs]"
echo "  [6] v6e-1 TPU   (32 GB HBM)            - Google TPU v6e Trillium"
echo "  [7] v5e-1 TPU   (16 GB HBM)            - Google TPU v5e"
echo ""
echo " [CPU]"
echo "  [8] CPU         (No GPU/TPU)           - Host CPU runtime (Prompts for High-RAM)"
echo "----------------------------------------------------------------------------------------"
read -l -P "Select an accelerator [1-8] (default: 1 [G4]): " accel_choice
if test -z "$accel_choice"
    set accel_choice "1"
end

set -l PROVISION_CMD colab new -s "$SESSION_NAME"
set -l SELECTED_LABEL ""

switch "$accel_choice"
    case "1" "g4" "G4"
        set PROVISION_CMD $PROVISION_CMD --gpu G4
        set SELECTED_LABEL "NVIDIA RTX PRO 6000 Blackwell G4 GPU (96 GB GDDR7 VRAM)"
    case "2" "a100" "A100"
        set PROVISION_CMD $PROVISION_CMD --gpu A100
        set SELECTED_LABEL "NVIDIA A100 GPU (40GB/80GB HBM2e VRAM)"
    case "3" "l4" "L4"
        set PROVISION_CMD $PROVISION_CMD --gpu L4
        set SELECTED_LABEL "NVIDIA L4 GPU (24 GB GDDR6 VRAM)"
    case "4" "t4" "T4"
        set PROVISION_CMD $PROVISION_CMD --gpu T4
        set SELECTED_LABEL "NVIDIA T4 GPU (16 GB GDDR6 VRAM)"
    case "5" "h100" "H100"
        set PROVISION_CMD $PROVISION_CMD --gpu H100
        set SELECTED_LABEL "NVIDIA H100 GPU (80 GB HBM3 VRAM)"
    case "6" "v6e" "v6e1" "v6e-1"
        set PROVISION_CMD $PROVISION_CMD --tpu v6e1
        set SELECTED_LABEL "Google TPU v6e Trillium (32 GB HBM)"
    case "7" "v5e" "v5e1" "v5e-1"
        set PROVISION_CMD $PROVISION_CMD --tpu v5e1
        set SELECTED_LABEL "Google TPU v5e (16 GB HBM)"
    case "8" "cpu" "CPU"
        echo -e "\nNo GPU/TPU selected. Configuring CPU runtime..."
        read -l -P "Do you want High-RAM for the CPU runtime (~53 GB system RAM)? [y/N]: " high_ram_choice
        if test "$high_ram_choice" = "y" -o "$high_ram_choice" = "Y" -o "$high_ram_choice" = "yes"
            set PROVISION_CMD $PROVISION_CMD --high-mem
            set SELECTED_LABEL "CPU Runtime (High-RAM ~53 GB system RAM)"
        else
            set SELECTED_LABEL "CPU Runtime (Standard RAM ~13 GB system RAM)"
        end
    case "*"
        echo "Unknown choice '$accel_choice', defaulting to G4 GPU."
        set PROVISION_CMD $PROVISION_CMD --gpu G4
        set SELECTED_LABEL "NVIDIA RTX PRO 6000 Blackwell G4 GPU (96 GB GDDR7 VRAM)"
end

echo -e "\nSession Name:         $SESSION_NAME"
echo "Selected Hardware:    $SELECTED_LABEL"
echo "Provisioning Command: $PROVISION_CMD"
echo "======================================================================"

# Guaranteed teardown function to release Colab VM and local session
function cleanup_session
    if test "$SESSION_PROVISIONED" -eq 1 -a "$CLEANUP_DONE" -eq 0
        set -g CLEANUP_DONE 1
        echo -e "\n==> Tearing down Colab VM ($SESSION_NAME) to release compute units..."

        set -l stop_attempt 1
        set -l stop_max 3
        set -l stopped 0
        while test $stop_attempt -le $stop_max
            if colab stop -s "$SESSION_NAME"
                set stopped 1
                echo "==> Colab session '$SESSION_NAME' closed successfully."
                break
            end
            if test $stop_attempt -lt $stop_max
                echo "Warning: 'colab stop' failed (attempt $stop_attempt/$stop_max). Retrying in 3s..."
                sleep 3
            end
            set stop_attempt (math $stop_attempt + 1)
        end

        if test $stopped -eq 0
            echo "Warning: 'colab stop -s $SESSION_NAME' did not return 0 after $stop_max attempts."
        end

        if test -n "$LOCAL_OUT"; and test -d "$LOCAL_OUT"; and not test -f "$LOCAL_OUT/model.ckpt"
            echo "==> Removing incomplete history folder from aborted run: $LOCAL_OUT"
            rm -rf "$LOCAL_OUT"
        end

        rm -f /tmp/code.tar.gz "/tmp/colab_exec_$SESSION_NAME.log"
    end
end

function _on_fish_exit --on-event fish_exit
    cleanup_session
end

function _on_signal --on-signal INT --on-signal TERM --on-signal HUP
    echo -e "\nInterrupt/termination signal received! Cleaning up Colab session before exiting..."
    cleanup_session
    exit 130
end

# Helper function for executing scripts on Colab with automatic retries for transient websocket drops
# Also detects unhandled Python exceptions inside the Colab IPython kernel (which colab exec otherwise exits 0 on)
function colab_exec_retry
    set -l session $argv[1]
    set -l timeout $argv[2]
    set -l file $argv[3]
    set -l exec_log "/tmp/colab_exec_$session.log"

    echo "Executing on Colab: "(path basename "$file")
    rm -f "$exec_log"
    colab exec -s "$session" --timeout "$timeout" -f "$file" 2>&1 | tee "$exec_log"
    set -l exec_rc $pipestatus[1]

    if test $exec_rc -eq 130 -o $exec_rc -eq 143
        echo "Execution interrupted by signal (code $exec_rc). Aborting..."
        return $exec_rc
    end

    if test -f "$exec_log"; and grep -E -q "(Traceback \(most recent call last\)|SyntaxError:|NameError:|Exception:)" "$exec_log"
        echo "Error: Python exception detected while running "(path basename "$file")" on Colab."
        return 1
    end

    if test $exec_rc -ne 0
        echo "Error: Execution failed with exit code $exec_rc."
        return $exec_rc
    end

    return 0
end

# 1. Provision Colab VM
echo -e "\n[1/8] Provisioning Colab VM ($SELECTED_LABEL)..."
set -g SESSION_PROVISIONED 1
if not eval $PROVISION_CMD
    echo "Error: Failed to provision Colab VM with $SELECTED_LABEL."
    exit 1
end
sleep 3

# 2. Mount Google Drive (fail-fast: aborts and terminates Colab VM immediately on error)
echo -e "\n[2/8] Mounting Google Drive..."
echo "IMPORTANT: When the OAuth link appears, open it in your browser, click 'Allow',"
echo "and wait until the browser confirms authorization BEFORE pressing Enter here!"

echo "--> Executing Google Drive mount on Colab VM..."
if not colab drivemount -s "$SESSION_NAME"
    echo "======================================================================"
    echo "FATAL ERROR: 'colab drivemount' command failed!"
    echo "Google Drive could not be mounted. Killing Colab VM and aborting pipeline..."
    echo "======================================================================"
    cleanup_session
    exit 1
end

sleep 2
set -l verify_out (colab exec -s "$SESSION_NAME" --timeout 60 -f "$LOCAL_REPO/google_colab/verify_drive.py" 2>&1)
if not string match -q "*DRIVE_MOUNT_VERIFIED_OK*" "$verify_out"
    echo "======================================================================"
    echo "FATAL ERROR: Google Drive mount verification failed (/content/drive/MyDrive is not mounted)!"
    echo "Verification output:"
    echo "$verify_out"
    echo "Killing Colab VM immediately to save compute units and aborting pipeline..."
    echo "======================================================================"
    cleanup_session
    exit 1
end

echo "==> Google Drive successfully mounted and verified at /content/drive/MyDrive!"

# 3. Package and Upload Local Code
echo -e "\n[3/8] Packaging and uploading local codebase to Colab..."
if not tar --exclude=".git" \
    --exclude=".env" \
    --exclude=".venv" \
    --exclude="venv" \
    --exclude="__pycache__" \
    --exclude="*.pyc" \
    --exclude="*.ckpt" \
    --exclude="*.png" \
    --exclude="*.ipynb" \
    --exclude="*.root" \
    --exclude="*Zone.Identifier" \
    --exclude="experiments" \
    --exclude="scratch" \
    --exclude=".idea" \
    --exclude=".vscode" \
    -czf /tmp/code.tar.gz -C "$LOCAL_REPO" .
    echo "Error: Failed to create local code archive."
    exit 1
end
if not colab upload -s "$SESSION_NAME" /tmp/code.tar.gz /content/code.tar.gz
    echo "Error: Failed to upload code archive."
    exit 1
end

# Extract archive on Colab using unpack.py
echo "Extracting code on Colab..."
if not colab_exec_retry "$SESSION_NAME" 120 "$LOCAL_REPO/google_colab/unpack.py"
    echo "Error: Code extraction failed."
    exit 1
end

# Prepare and upload runtime .env with FLAG_NAME and RUN_TIMESTAMP (after unpack so it is never overwritten)
set -l RUNTIME_ENV "/tmp/runtime_$SESSION_NAME.env"
if test -f "$LOCAL_REPO/.env"
    cp "$LOCAL_REPO/.env" "$RUNTIME_ENV"
else
    touch "$RUNTIME_ENV"
end
echo "" >> "$RUNTIME_ENV"
echo "FLAG_NAME=$FLAG_NAME" >> "$RUNTIME_ENV"
echo "RUN_TIMESTAMP=$RUN_TIMESTAMP" >> "$RUNTIME_ENV"
colab upload -s "$SESSION_NAME" "$RUNTIME_ENV" /content/.env
colab upload -s "$SESSION_NAME" "$RUNTIME_ENV" /content/code/.env >/dev/null 2>&1
cp "$RUNTIME_ENV" "$LOCAL_OUT/.env"
rm -f "$RUNTIME_ENV"
sleep 2

# 4. Setup Python Environment with UV
echo -e "\n[4/8] Installing dependencies on Colab with uv..."
if not colab_exec_retry "$SESSION_NAME" 300 "$LOCAL_REPO/google_colab/setup_env.py"
    echo "Error: Environment setup failed."
    exit 1
end

# 5. Inspect Google Drive Data
echo -e "\n[5/8] Inspecting Google Drive datasets..."
if not colab_exec_retry "$SESSION_NAME" 120 "$LOCAL_REPO/google_colab/inspect_drive.py"
    echo "======================================================================"
    echo "Error: Google Drive dataset inspection failed!"
    echo "Required path: /content/drive/MyDrive/monografia/dados/{train, test, validacao}"
    echo "To download and synchronize the JetClass dataset from Zenodo, run:"
    echo "  ./google_colab/download_data.fish"
    echo "======================================================================"
    cleanup_session
    exit 1
end

# 6. Stage Data to Local Fast NVMe (3 files/jet for train = 3M, 1 file/jet for test = 1M)
echo -e "\n[6/8] Staging data to local NVMe storage (3M train / 1M test)..."
if not colab_exec_retry "$SESSION_NAME" 1800 "$LOCAL_REPO/google_colab/stage_data.py"
    echo "Error: Data staging failed."
    exit 1
end

# 7. Run Model Pipeline via target model's main.py
echo -e "\n[7/8] Running $MODEL_TARGET Pipeline ($MODEL_RUNNER_REL)..."
if not colab_exec_retry "$SESSION_NAME" 10800 "$MODEL_RUNNER_FULL"
    echo "Error: Training execution failed."
    exit 1
end

# 8. Download Trained Artifacts (Final Model, Summaries & Metrics) to Versioned Experiments Folder
echo -e "\n[8/8] Downloading trained artifacts to local experiment folder ($LOCAL_OUT)..."
set -l local_tar "$LOCAL_OUT/output_artifacts.tar.gz"
if colab download -s "$SESSION_NAME" /content/output_artifacts.tar.gz "$local_tar"
    tar -xzf "$local_tar" -C "$LOCAL_OUT"
    rm -f "$local_tar"
    echo "Artifacts successfully saved to $LOCAL_OUT:"
    echo " - Final Model Checkpoint:   $LOCAL_OUT/model.ckpt"
    echo " - Best Model Checkpoint:    $LOCAL_OUT/best_model.ckpt"
    echo " - Summary Overview (CSV):   $LOCAL_OUT/summary.csv"
    echo " - Experiment Metadata:      $LOCAL_OUT/metadata.json"
    echo " - Epoch Metrics (CSV):      $LOCAL_OUT/epoch_metrics.csv"
    echo " - Checkpoint Metrics (CSV): $LOCAL_OUT/checkpoint_metrics.csv"
    echo " - Reconstruction Report:    $LOCAL_OUT/reconstruction_metrics.txt"
    echo " - Physics Diagnostics JSON: $LOCAL_OUT/physics_metrics.json"
    echo " - Pointwise Metrics (CSV):  $LOCAL_OUT/pointwise_metrics.csv"
    echo " - Jet Physics (CSV):        $LOCAL_OUT/jet_physics_metrics.csv"
    echo " - Visualizations:           $LOCAL_OUT/latent_2d.png"
    echo " - Google Drive Checkpoints: /content/drive/MyDrive/monografia/modelos/$FLAG_NAME/$RUN_TIMESTAMP/checkpoints/"
else if colab download -s "$SESSION_NAME" /content/output/model.ckpt "$LOCAL_OUT/model.ckpt"
    and colab download -s "$SESSION_NAME" /content/output/latent_2d.png "$LOCAL_OUT/latent_2d.png"
    colab download -s "$SESSION_NAME" /content/output/best_model.ckpt "$LOCAL_OUT/best_model.ckpt" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/summary.csv "$LOCAL_OUT/summary.csv" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/metadata.json "$LOCAL_OUT/metadata.json" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/epoch_metrics.csv "$LOCAL_OUT/epoch_metrics.csv" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/checkpoint_metrics.csv "$LOCAL_OUT/checkpoint_metrics.csv" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/reconstruction_metrics.txt "$LOCAL_OUT/reconstruction_metrics.txt" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/physics_metrics.json "$LOCAL_OUT/physics_metrics.json" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/pointwise_metrics.csv "$LOCAL_OUT/pointwise_metrics.csv" >/dev/null 2>&1
    colab download -s "$SESSION_NAME" /content/output/jet_physics_metrics.csv "$LOCAL_OUT/jet_physics_metrics.csv" >/dev/null 2>&1
    echo "Artifacts downloaded to: $LOCAL_OUT"
else
    echo "Warning: Could not download output artifacts."
end

# Cleanup and tear down VM (also guaranteed by fish_exit trap)
cleanup_session
echo "Pipeline complete! Run history archived at: $LOCAL_OUT"
