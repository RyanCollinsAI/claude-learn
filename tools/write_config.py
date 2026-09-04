"""Write a fresh config.json for the learn skill.

  python3 write_config.py <config-path> <vault-root> <vault-name> <learning-dir> <course-dir>

Only called by install.sh, and only when there is no config.json already.
"""
import json
import os
import sys

path, vault, name, learning, course = sys.argv[1:6]
vault = os.path.abspath(vault)
learning = learning.strip("/") or "Learning"
cfg = {
    "vault_root": vault,
    "obsidian_vault_name": name or os.path.basename(vault),
    "learning_dir": learning,
    "course_learning_dir": course.strip("/"),
    "learner_file": learning + "/LEARNER.md",
    "quiz_log_dir": learning + "/.quiz-log",
    "visuals_dir": learning + "/visuals",
    "chrome_path": "",
    "terminal_process": "",
}
with open(path, "w", encoding="utf-8") as fh:
    json.dump(cfg, fh, indent=2)
    fh.write("\n")
for k, v in cfg.items():
    print("  %-20s %s" % (k, v))
