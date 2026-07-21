"""Verify every dependency in requirements.txt is importable. Exit 1 if any missing."""
import importlib
import sys
import os

req_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "requirements.txt")
if not os.path.exists(req_file):
    sys.exit(0)

IMPORT_NAMES = {
    "google-genai": "google.genai",
    "scikit-learn": "sklearn",
    "Pillow": "PIL",
    "opencv-python": "cv2",
    "python-dotenv": "dotenv",
    "pyyaml": "yaml",
    "beautifulsoup4": "bs4",
    "cryptography": "cryptography",
}

missing = []
with open(req_file) as f:
    for line in f:
        pkg = line.strip()
        if not pkg or pkg.startswith("#"):
            continue
        pkg_name = pkg.split("[")[0].split(">")[0].split("<")[0].split("=")[0].split("~")[0].strip()
        mod_name = IMPORT_NAMES.get(pkg_name, pkg_name.replace("-", "_").replace(".", "_"))
        try:
            importlib.import_module(mod_name)
        except ModuleNotFoundError:
            missing.append(pkg)

if missing:
    print(f"MISSING: {' '.join(missing)}")
    sys.exit(1)
