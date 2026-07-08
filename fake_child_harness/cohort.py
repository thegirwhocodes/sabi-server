from __future__ import annotations

from dataclasses import asdict, dataclass
import random
from typing import Any


LANGUAGE_PROFILES = (
    "nigerian_english",
    "pidgin_influenced_english",
    "yoruba_code_switch",
    "hausa_code_switch",
    "igbo_code_switch",
)

SCHOOL_STATUSES = ("in_school", "out_of_school", "irregular_attendance")
TEMPERAMENTS = ("shy", "eager", "talkative", "distracted", "guesses", "interrupts", "silent")
ENVIRONMENTS = ("quiet_home", "shared_room", "busy_compound", "bus_stop", "lagos_market")
CALL_BEHAVIORS = ("steady", "hangs_up_early", "misses_turns", "repeats_answer", "changes_answer")
NOISE_LEVELS = ("clean", "home", "busy_compound", "lagos_market", "brutal_market")
STT_RISKS = (
    "soft_speech",
    "short_numbers",
    "name_confusion",
    "code_switching",
    "background_speech",
    "carrier_audio",
)


@dataclass(frozen=True)
class FakeChildProfile:
    child_id: str
    display_name: str
    age: int
    gender: str
    language_profile: str
    school_status: str
    literacy_level: int
    numeracy_level: int
    temperament: str
    environment: str
    noise_level: str
    stt_risks: tuple[str, ...]
    call_behavior: str

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["stt_risks"] = list(self.stt_risks)
        return data


def generate_cohort(count: int = 100, seed: int = 20260706) -> list[FakeChildProfile]:
    rng = random.Random(seed)
    cohort: list[FakeChildProfile] = []

    for idx in range(1, count + 1):
        age = rng.randint(8, 14)
        environment = _weighted_choice(
            rng,
            {
                "quiet_home": 0.18,
                "shared_room": 0.22,
                "busy_compound": 0.28,
                "bus_stop": 0.16,
                "lagos_market": 0.16,
            },
        )
        if environment == "lagos_market":
            noise_level = _weighted_choice(rng, {"lagos_market": 0.7, "brutal_market": 0.3})
        elif environment in {"bus_stop", "busy_compound"}:
            noise_level = _weighted_choice(rng, {"busy_compound": 0.65, "lagos_market": 0.25, "home": 0.1})
        else:
            noise_level = _weighted_choice(rng, {"clean": 0.35, "home": 0.65})

        risks = _sample_risks(rng, environment, noise_level)
        cohort.append(
            FakeChildProfile(
                child_id=f"FC-{idx:03d}",
                display_name=f"Fake Child {idx:03d}",
                age=age,
                gender="girl" if idx % 2 else "boy",
                language_profile=_weighted_choice(
                    rng,
                    {
                        "nigerian_english": 0.45,
                        "pidgin_influenced_english": 0.28,
                        "yoruba_code_switch": 0.14,
                        "hausa_code_switch": 0.07,
                        "igbo_code_switch": 0.06,
                    },
                ),
                school_status=_weighted_choice(
                    rng,
                    {"in_school": 0.45, "out_of_school": 0.25, "irregular_attendance": 0.30},
                ),
                literacy_level=_clamped_level(rng),
                numeracy_level=_clamped_level(rng),
                temperament=rng.choice(TEMPERAMENTS),
                environment=environment,
                noise_level=noise_level,
                stt_risks=risks,
                call_behavior=_weighted_choice(
                    rng,
                    {
                        "steady": 0.58,
                        "hangs_up_early": 0.08,
                        "misses_turns": 0.12,
                        "repeats_answer": 0.12,
                        "changes_answer": 0.10,
                    },
                ),
            )
        )
    return cohort


def cohort_to_jsonable(cohort: list[FakeChildProfile]) -> list[dict[str, Any]]:
    return [child.to_dict() for child in cohort]


def _weighted_choice(rng: random.Random, weights: dict[str, float]) -> str:
    total = sum(weights.values())
    pick = rng.random() * total
    running = 0.0
    for key, weight in weights.items():
        running += weight
        if pick <= running:
            return key
    return next(reversed(weights))


def _clamped_level(rng: random.Random) -> int:
    # Skew toward beginner levels while preserving a few stronger learners.
    return max(0, min(5, int(rng.triangular(0, 5, 1.4))))


def _sample_risks(rng: random.Random, environment: str, noise_level: str) -> tuple[str, ...]:
    risks: set[str] = set()
    if environment in {"busy_compound", "bus_stop", "lagos_market"}:
        risks.add("background_speech")
    if noise_level in {"lagos_market", "brutal_market"}:
        risks.add("short_numbers")
    if rng.random() < 0.22:
        risks.add("soft_speech")
    if rng.random() < 0.18:
        risks.add("code_switching")
    if rng.random() < 0.08:
        risks.add("name_confusion")
    if rng.random() < 0.03:
        risks.add("carrier_audio")
    return tuple(sorted(risks))

