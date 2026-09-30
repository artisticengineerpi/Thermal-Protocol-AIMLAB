"""Identify and synchronize the Uno to OFF. Never sends a stimulation command."""
import argparse
import json
from pathlib import Path
import time
from aimlab.connector import UnoConnector, is_off
from aimlab.storage import atomic_json, utc_now

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--port')
    args = parser.parse_args()
    link = UnoConnector(preferred_port=args.port)
    link.start()
    success = False
    try:
        deadline = time.monotonic()+12
        previous = None
        while time.monotonic() < deadline:
            link.pulse()
            state = link.snapshot()
            message = (state['state'], state['detail'])
            if message != previous:
                print(' | '.join(message), flush=True)
                previous = message
            if state['state'] == 'READY' and is_off(state['telemetry']):
                success = True
                break
            time.sleep(.025)
        report = {'utc': utc_now(), 'passed': success, 'snapshot': link.snapshot(),
                  'scope': 'USB firmware handshake and reported all-OFF outputs only; no stimulation or physical sensor check'}
        atomic_json(Path(__file__).resolve().parent/'validation/last-connection-check.json', report)
        print(json.dumps(report, indent=2))
    finally:
        link.close()
    return 0 if success else 1

if __name__ == '__main__':
    raise SystemExit(main())
