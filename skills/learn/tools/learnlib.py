"""Config for the learn skill's tools.

Nothing personal is hardcoded. `config.json` next to SKILL.md supplies the
machine-specific values, and every key has a default, so the tools run on a
fresh clone with no config file at all. See `config.example.json`.

Any key can be overridden for one run with `LEARN_<KEY>`, e.g. LEARN_VAULT_ROOT.
"""
import json
import os
import platform
import shutil

SKILL = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(SKILL, "config.json")


def _read_config():
    try:
        with open(CONFIG_PATH, encoding="utf-8") as fh:
            d = json.load(fh)
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


CONFIG = _read_config()


def cfg(key, default=None):
    """A config value, with the environment able to override it (LEARN_<KEY>)."""
    v = os.environ.get("LEARN_" + key.upper())
    if v:
        return v
    v = CONFIG.get(key)
    # A key present but blank means "use the default", not "use an empty string".
    # config.example.json ships several keys blank for exactly that reason.
    return default if v in (None, "") else v


VAULT_ROOT = os.path.abspath(cfg("vault_root", os.getcwd()))
VAULT_NAME = cfg("obsidian_vault_name", os.path.basename(VAULT_ROOT))
LEARNING_DIR = cfg("learning_dir", "Learning")
COURSE_LEARNING_DIR = cfg("course_learning_dir", "")
LEARNER_FILE = cfg("learner_file", LEARNING_DIR + "/LEARNER.md")
QUIZ_LOG_DIR = cfg("quiz_log_dir", LEARNING_DIR + "/.quiz-log")
VISUALS_DIR = cfg("visuals_dir", LEARNING_DIR + "/visuals")

# The usual install paths, most likely first. Only used when chrome_path is unset.
_CHROME_CANDIDATES = {
    "Windows": [
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Google\Chrome\Application\chrome.exe"),
    ],
    "Darwin": [
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
    ],
    "Linux": [
        "/usr/bin/google-chrome",
        "/usr/bin/chromium-browser",
        "/usr/bin/chromium",
    ],
}


def chrome_path():
    """The Chrome binary both render tools drive headless.

    Returns None when nothing is found, so the caller can print a clear message
    naming `chrome_path` rather than failing inside subprocess with a WinError.
    """
    explicit = cfg("chrome_path", "")
    if explicit:
        return explicit
    for path in _CHROME_CANDIDATES.get(platform.system(), []):
        if os.path.exists(path):
            return path
    for name in ("google-chrome", "chromium", "chromium-browser", "chrome"):
        found = shutil.which(name)
        if found:
            return found
    return None


def vault_path(rel):
    """An absolute path from a vault-relative one, forward slashes accepted."""
    return os.path.join(VAULT_ROOT, rel.replace("/", os.sep))
