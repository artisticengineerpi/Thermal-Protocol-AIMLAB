"""Display connection health without disclosing the current trial condition."""

def connection_is_fresh(snapshot, now):
    return (snapshot["state"] in ("READY", "RUNNING")
            and snapshot.get("telemetry") is not None
            and 0 <= now-snapshot.get("status_at", 0) <= .65)