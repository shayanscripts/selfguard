"""Compile every SelfGuard test result into one zip in your Downloads folder, ready to export.

  python eval/collect_results.py                 # -> ~/Downloads/selfguard-v3.4-results-<date>-<time>.zip
  python eval/collect_results.py --no-cache      # leave out raw generation caches (smaller)
  python eval/collect_results.py --out D:\\exports

The zip holds:
  RESULTS.md        every report found, one after another, plus the run environment
  environment.json  Python, OS, CPU/GPU, git commit and status, SelfGuard version, Ollama models
  results/...       the result files (.json, .md) written by the eval scripts in this repo
  cache/...         raw model replies (SEP generation caches) unless --no-cache
Never included: data/ (SEP rows are not redistributable; sealed rows must stay unread).
"""
import argparse
import datetime
import glob
import json
import os
import platform
import subprocess
import sys
import urllib.request
import zipfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, HERE)
# every report the eval scripts write (v3.0's results live in archive/v3.0/results)
REPORT_GLOBS = ["sep_*", "bipia_*", "agentdojo_*", "agent_suite*", "smoke_*", "canary_small*", "leak_analysis_*"]


def run(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=HERE).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def environment(ollama_url):
    import selfguard3
    env = {"collected_at": datetime.datetime.now().isoformat(timespec="seconds"),
           "python": sys.version, "platform": platform.platform(), "processor": platform.processor(),
           "selfguard_version": selfguard3.__version__,
           "git_commit": run(["git", "rev-parse", "HEAD"]), "git_branch": run(["git", "branch", "--show-current"]),
           "git_dirty_files": run(["git", "status", "--porcelain"]),
           "gpu": run(["nvidia-smi", "--query-gpu=name,memory.total,driver_version", "--format=csv,noheader"])}
    try:
        with urllib.request.urlopen(ollama_url.rstrip("/") + "/api/tags", timeout=10) as r:
            env["ollama_models"] = [{"name": m.get("name"), "digest": m.get("digest"), "details": m.get("details")}
                                    for m in json.load(r).get("models", [])]
        with urllib.request.urlopen(ollama_url.rstrip("/") + "/api/version", timeout=10) as r:
            env["ollama_version"] = json.load(r).get("version")
    except Exception as e:  # Ollama not running: still collect the rest
        env["ollama_models"] = f"unavailable: {type(e).__name__}"
    return env


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(os.path.expanduser("~"), "Downloads"))
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--ollama", default="http://127.0.0.1:11434")
    a = ap.parse_args()
    results = os.path.join(HERE, "results")
    files = sorted({p for g in REPORT_GLOBS for p in glob.glob(os.path.join(results, g))
                    if os.path.isfile(p)})
    caches = [] if a.no_cache else sorted(glob.glob(os.path.join(results, "cache", "sep_*.jsonl")))
    if not files:
        sys.exit("no results found in results/: run the tests in TESTING_PLAN.md first")
    env = environment(a.ollama)
    md = ["# SelfGuard v3.4 test results", "", f"Collected {env['collected_at']} from commit `{env['git_commit']}` "
          f"(branch {env['git_branch']}, SelfGuard {env['selfguard_version']}).",
          f"GPU: {env['gpu'] or 'none found'}. Uncommitted changes: {'yes' if env['git_dirty_files'] else 'no'}.", ""]
    for p in files:
        if p.endswith(".md"):
            md += [f"## {os.path.basename(p)}", "", open(p, encoding="utf-8").read().strip(), ""]
    md += ["## Files", ""] + [f"- results/{os.path.basename(p)}" for p in files] + \
          [f"- cache/{os.path.basename(p)}" for p in caches]
    os.makedirs(a.out, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    dst = os.path.join(a.out, f"selfguard-v3.4-results-{stamp}.zip")
    with zipfile.ZipFile(dst, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("RESULTS.md", "\n".join(md) + "\n")
        z.writestr("environment.json", json.dumps(env, indent=1))
        for p in files:
            z.write(p, "results/" + os.path.basename(p))
        for p in caches:
            z.write(p, "cache/" + os.path.basename(p))
    print(f"wrote {dst} ({os.path.getsize(dst) / 1e6:.1f} MB): {len(files)} result files, {len(caches)} caches")


if __name__ == "__main__":
    main()
