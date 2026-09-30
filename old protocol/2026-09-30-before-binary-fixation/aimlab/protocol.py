"""Pure protocol definitions; no display or serial side effects."""
from dataclasses import dataclass, asdict
import random

ROWS = ("ABDC", "BCAD", "CDBA", "DACB")
CONDITIONS = {"A": "No stimulation", "B": "Thermal", "C": "Vibration", "D": "Combined"}
RESPONSES = {1: "No sensation", 2: "Static thermal", 3: "Moving vibration",
             4: "Moving thermal", 5: "Not sure"}
FIRMWARE_ID = "AIMLAB_COMBINED_V7"


@dataclass(frozen=True)
class Settings:
    motor_pwm: int = 189
    lead_ms: int = 980
    thermal_pwm: int = 183
    motion_ms: int = 4000
    polarity: str = "H"

    def __post_init__(self):
        for name, low, high in (("motor_pwm", 0, 255), ("lead_ms", 0, 2000),
                                ("thermal_pwm", 0, 255), ("motion_ms", 1000, 8000)):
            value = getattr(self, name)
            if type(value) is not int or not low <= value <= high:
                raise ValueError(f"Invalid {name}: {value}")
        if self.motion_ms % 100 or self.polarity != "H":
            raise ValueError("Study requires HOT and motion in 100 ms increments")

    def command(self, condition):
        if condition not in "ABCDEFGH" or len(condition) != 1:
            raise ValueError("Unknown condition")
        m = self.motor_pwm
        return (f"RUN {condition} H {self.thermal_pwm} {m} {m} {m} {m} "
                f"{self.lead_ms} {self.motion_ms}")

    def duration_s(self, condition):
        # Preserve the installed v7 timing: A/B and individual motors are 5 s.
        if condition == "D":
            return (self.lead_ms + self.motion_ms) / 1000
        if condition == "C":
            return self.motion_ms / 1000
        return 5.0

    def to_dict(self):
        return asdict(self)


def sequence(seed, blocks=5, repetitions=2, fixation_min=3., fixation_max=4.5):
    """Preserve the existing fixed row order. Seed randomizes fixation only."""
    rng = random.Random(seed)
    trials = []
    block_letters = "".join(ROWS) * repetitions
    for block in range(1, blocks + 1):
        for within, condition in enumerate(block_letters, 1):
            trials.append({"index": len(trials), "block": block, "within": within,
                           "condition": condition,
                           "fixation_s": rng.uniform(fixation_min, fixation_max)})
    return trials


def validate_study(config):
    Settings(config["initial_motor_pwm"], config["initial_lead_ms"],
             config["thermal_pwm"], config["motion_ms"], config["polarity"])
    if config["blocks"] != 5 or config["row_repetitions"] != 2:
        raise ValueError("This study requires 5 blocks and 2 row repetitions (160 trials)")
    if not 0 < config["fixation_min_s"] <= config["fixation_max_s"] <= 30:
        raise ValueError("Invalid fixation range")
    for field in ("response_delay_s", "break_s", "tone_duration_s"):
        if not 0 < config[field] <= 120:
            raise ValueError(f"Invalid {field}")
