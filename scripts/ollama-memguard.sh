#!/usr/bin/env bash
# Stops the bench Ollama container before the desktop runs out of memory.
#
# On AMD/ROCm, GPU memory that overflows VRAM is pinned in system RAM (GTT). Swap can't take it and the kernel
# OOM killer can't attribute it to Ollama, so without this the OOM killer takes down the desktop instead.
# Generation writes its output incrementally, so stopping Ollama loses at most the requests in flight.
#
#   scripts/ollama-memguard.sh &            # run next to a generation run; exits after stopping Ollama
#
# Settings (environment): MIN_AVAILABLE_MIB (default 4096), MAX_GTT_MIB (default 6144), INTERVAL (seconds, 5),
# CONTAINER (nai-bench-ollama-1).
set -euo pipefail

MIN_AVAILABLE_MIB=${MIN_AVAILABLE_MIB:-4096}
MAX_GTT_MIB=${MAX_GTT_MIB:-6144}
INTERVAL=${INTERVAL:-5}
CONTAINER=${CONTAINER:-nai-bench-ollama-1}

gtt_file=$(ls /sys/class/drm/card*/device/mem_info_gtt_used 2>/dev/null | head -1 || true)

available_mib() { awk '/^MemAvailable:/ {print int($2 / 1024)}' /proc/meminfo; }
gtt_mib() { if [[ -n $gtt_file ]]; then echo $(( $(cat "$gtt_file") / 1048576 )); else echo 0; fi; }
log() { echo "$(date '+%F %T') memguard: $*"; }

log "watching $CONTAINER: stop if RAM available < ${MIN_AVAILABLE_MIB} MiB or GPU GTT > ${MAX_GTT_MIB} MiB"
while true; do
    if [[ $(docker inspect -f '{{.State.Running}}' "$CONTAINER" 2>/dev/null) != true ]]; then
        log "$CONTAINER is not running; exiting"
        exit 0
    fi
    available=$(available_mib)
    gtt=$(gtt_mib)
    if (( available < MIN_AVAILABLE_MIB || gtt > MAX_GTT_MIB )); then
        log "STOPPING $CONTAINER (RAM available ${available} MiB, GTT ${gtt} MiB)"
        docker stop -t 5 "$CONTAINER" >/dev/null || docker kill "$CONTAINER" >/dev/null
        exit 1
    fi
    sleep "$INTERVAL"
done
