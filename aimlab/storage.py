"""Atomic session snapshots and flushed, append-only event/attempt records."""
import csv
import json
import os
from pathlib import Path
import re
import time
import uuid
from datetime import datetime, timezone


def utc_now():
    return datetime.now(timezone.utc).isoformat()


def atomic_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, ensure_ascii=False, allow_nan=False)
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


class Session:
    FIELDS = ["attempt_id", "index", "block", "within", "condition", "status",
              "reason", "response", "response_label", "rt_s", "fixation_s",
              "motor_pwm", "thermal_pwm", "lead_ms", "motion_ms", "polarity",
              "started_utc", "finished_utc", "run_sent_monotonic", "ack_monotonic",
              "done_monotonic", "generation", "dropped_frames"]

    @classmethod
    def create(cls, root, participant, config, trials, seed):
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", participant):
            raise ValueError("Participant ID: use 1–40 letters, numbers, underscores or hyphens")
        folder = Path(root) / (participant + "_" + datetime.now().strftime("%Y%m%d_%H%M%S")
                               + "_" + uuid.uuid4().hex[:6])
        folder.mkdir(parents=True, exist_ok=False)
        atomic_json(folder / "session.json", {"schema": 1, "participant": participant,
                    "created_utc": utc_now(), "config": config, "seed": seed,
                    "trials": trials, "next_index": 0, "calibration": None,
                    "calibration_locked": False, "status": "calibration"})
        return cls(folder)

    def __init__(self, folder):
        self.folder = Path(folder)
        self.state = json.loads((self.folder / "session.json").read_text(encoding="utf-8"))
        # The committed attempts journal is authoritative if a crash happened
        # between writing a response and replacing the session snapshot.
        completed = set()
        path = self.folder / "attempts.jsonl"
        records = []
        if path.exists():
            raw = path.read_bytes()
            if raw and not raw.endswith(b"\n"):
                # Preserve a torn final record, then restore an append boundary.
                boundary = raw.rfind(b"\n") + 1
                (self.folder / ("torn-record-" + uuid.uuid4().hex[:8] + ".bin")).write_bytes(raw[boundary:])
                path.write_bytes(raw[:boundary])
            for line in path.read_text(encoding="utf-8").splitlines():
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue  # an interrupted final write is not a completed trial
                records.append(record)
                if record.get("status") == "complete":
                    completed.add(record["index"])
        active = self.state.pop("active_attempt", None)
        if active and not any(r["attempt_id"] == active["attempt_id"] for r in records):
            interrupted = {**active, "status": "aborted", "reason": "Application interrupted; recovered on resume",
                           "finished_utc": utc_now()}
            self.append("attempts.jsonl", interrupted)
            records.append(interrupted)
        # Rebuild the convenient CSV from the durable journal after a crash.
        if records:
            with (self.folder / "trials.csv").open("w", newline="", encoding="utf-8") as f:
                writer = csv.DictWriter(f, fieldnames=self.FIELDS, extrasaction="ignore")
                writer.writeheader()
                writer.writerows(records)
        index = 0
        while index in completed:
            index += 1
        self.state["next_index"] = index
        if index == len(self.state["trials"]):
            self.state["status"] = "complete"
        self.save()

    def save(self):
        atomic_json(self.folder / "session.json", self.state)

    def append(self, filename, record, durable=True):
        with (self.folder / filename).open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False, allow_nan=False) + "\n")
            f.flush()
            if durable:
                os.fsync(f.fileno())

    def event(self, kind, **values):
        self.append("events.jsonl", {"utc": utc_now(), "monotonic": time.monotonic(),
                                     "kind": kind, **values}, durable=kind not in ("telemetry", "serial_tx"))

    def finish_attempt(self, record):
        self.append("attempts.jsonl", record)
        path = self.folder / "trials.csv"
        new = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=self.FIELDS, extrasaction="ignore")
            if new:
                writer.writeheader()
            writer.writerow(record)
            f.flush()
            os.fsync(f.fileno())
        if record["status"] == "complete":
            self.state["next_index"] = record["index"] + 1
        self.save()

    def calibrate(self, settings, note="", lock=False):
        self.state["calibration"] = settings.to_dict()
        self.state["calibration_note"] = note
        self.state["calibration_locked"] = lock
        self.event("calibration_saved", settings=settings.to_dict(), note=note, locked=lock)
        self.save()
