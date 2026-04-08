"""
Training watcher — monitors val loss every checkpoint and stops training
if overfitting is detected (val loss rising while train still falling).

Overfitting rule: val loss rises above its all-time minimum by PATIENCE
consecutive checkpoints → kill training, log best checkpoint.
"""

import re
import signal
import subprocess
import time
from pathlib import Path

LOG_PATH = Path("/home/prana/project-seishin/dataset_pipeline/logs/phase5e_training.log")
WATCHER_LOG = Path("/home/prana/project-seishin/dataset_pipeline/logs/watcher.log")
CKPT_DIR = Path("/home/prana/fish-speech/results/text2semantic_finetune_dual_ar/checkpoints")

# How many consecutive val loss increases before we stop
PATIENCE = 2
# Minimum improvement to count as "still improving"
MIN_DELTA = 0.01
# How often to poll the log (seconds)
POLL_INTERVAL = 60

def get_training_pid():
    try:
        result = subprocess.run(
            ["pgrep", "-f", "fish_speech/train.py"],
            capture_output=True, text=True
        )
        pids = result.stdout.strip().split()
        return int(pids[0]) if pids else None
    except Exception:
        return None

def parse_metrics(log_text):
    """Extract (step, train_loss, val_loss) tuples from log."""
    # Val loss lines look like: val/loss=5.950, val/top_5_accuracy=0.632
    val_pattern = re.compile(
        r"(\d+)/5000.*?train/loss=([\d.]+).*?val/loss=([\d.]+)"
    )
    results = []
    for m in val_pattern.finditer(log_text):
        step = int(m.group(1))
        train_loss = float(m.group(2))
        val_loss = float(m.group(3))
        results.append((step, train_loss, val_loss))
    # Deduplicate by step, keep last
    seen = {}
    for item in results:
        seen[item[0]] = item
    return sorted(seen.values())

def log(msg, watcher_log):
    line = f"[{time.strftime('%H:%M:%S')}] {msg}"
    print(line, flush=True)
    with open(watcher_log, "a") as f:
        f.write(line + "\n")

def main():
    WATCHER_LOG.parent.mkdir(parents=True, exist_ok=True)
    log("Watcher started. Monitoring val loss every checkpoint (every ~13 min).", WATCHER_LOG)
    log(f"Rule: stop if val loss rises {PATIENCE} checkpoints in a row (min_delta={MIN_DELTA})", WATCHER_LOG)

    best_val = float("inf")
    best_step = 0
    rises_in_a_row = 0
    last_seen_step = 0

    while True:
        time.sleep(POLL_INTERVAL)

        pid = get_training_pid()
        if pid is None:
            log("Training process not found — it may have finished naturally.", WATCHER_LOG)
            log(f"Best val loss was {best_val:.4f} at step {best_step}", WATCHER_LOG)
            break

        try:
            log_text = LOG_PATH.read_text()
        except Exception as e:
            log(f"Could not read log: {e}", WATCHER_LOG)
            continue

        metrics = parse_metrics(log_text)
        if not metrics:
            continue

        # Only process new checkpoints
        new_metrics = [m for m in metrics if m[0] > last_seen_step]
        if not new_metrics:
            continue

        for step, train_loss, val_loss in new_metrics:
            last_seen_step = step
            improved = val_loss < (best_val - MIN_DELTA)

            if improved:
                best_val = val_loss
                best_step = step
                rises_in_a_row = 0
                log(f"Step {step:4d} | train={train_loss:.4f} | val={val_loss:.4f} | NEW BEST ✓", WATCHER_LOG)
            else:
                rises_in_a_row += 1
                delta = val_loss - best_val
                log(
                    f"Step {step:4d} | train={train_loss:.4f} | val={val_loss:.4f} | "
                    f"+{delta:.4f} above best (rise {rises_in_a_row}/{PATIENCE})",
                    WATCHER_LOG
                )

            if rises_in_a_row >= PATIENCE:
                log(
                    f"OVERFITTING DETECTED — val loss rose {PATIENCE} checkpoints in a row.",
                    WATCHER_LOG
                )
                log(f"Best checkpoint: step {best_step} with val_loss={best_val:.4f}", WATCHER_LOG)
                best_ckpt = CKPT_DIR / f"step_{best_step:09d}.ckpt"
                if best_ckpt.exists():
                    log(f"Best checkpoint file: {best_ckpt}", WATCHER_LOG)
                else:
                    # Find closest
                    ckpts = sorted(CKPT_DIR.glob("*.ckpt"))
                    log(f"Available checkpoints: {[c.name for c in ckpts]}", WATCHER_LOG)
                log(f"Stopping training (PID {pid})...", WATCHER_LOG)
                try:
                    import os
                    os.kill(pid, signal.SIGTERM)
                    time.sleep(5)
                    if get_training_pid():
                        os.kill(pid, signal.SIGKILL)
                    log("Training stopped.", WATCHER_LOG)
                except Exception as e:
                    log(f"Error stopping training: {e}", WATCHER_LOG)
                return

    log("Watcher exiting.", WATCHER_LOG)

if __name__ == "__main__":
    main()
