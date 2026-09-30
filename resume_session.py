"""Select an unfinished session before starting the serial worker."""
import json
from pathlib import Path
import subprocess
import sys
from psychopy import gui

root = Path(__file__).resolve().parent
sessions = []
for path in (root / "data").glob("*/session.json"):
    state = json.loads(path.read_text(encoding="utf-8"))
    if state["status"] != "complete":
        sessions.append(path.parent)
sessions.sort(key=lambda p: p.name, reverse=True)
if not sessions:
    print("No unfinished sessions found.")
else:
    selection = {"Session": [p.name for p in sessions]}
    if gui.DlgFromDict(selection, title="Resume AIMLAB session").OK:
        selected = next(p for p in sessions if p.name == selection["Session"])
        subprocess.run([sys.executable, str(root / "run_experiment.py"), "--resume", str(selected)], check=True)
