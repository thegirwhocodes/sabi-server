#!/usr/bin/env python3
"""Consent-, license-, and split-aware data mixing for Sabi STT training."""

from __future__ import annotations

import hashlib
import json
import logging
import random
import re
from collections import Counter
from pathlib import Path
from typing import Any, Iterable


LOGGER = logging.getLogger("whisper-finetune.data")
DEFAULT_SOURCE_RATIOS = {
    "nigerian_common_voice": 0.10,
    "sabi_corrected": 0.20,
    "general_english_retention": 0.15,
}
NONCOMMERCIAL_MARKERS = ("BY-NC", "NONCOMMERCIAL")


def stable_split(value: str) -> str:
    """Speaker-stable 90/5/5 split, preventing one voice leaking across sets."""
    bucket = int(hashlib.sha256(value.encode("utf-8")).hexdigest()[:8], 16) % 100
    if bucket < 90:
        return "train"
    if bucket < 95:
        return "dev"
    return "test"


def is_short_response(transcript: str, duration: float | None = None) -> bool:
    words = re.findall(r"[a-z0-9']+", str(transcript or "").lower())
    return len(words) <= 3 or (duration is not None and 0 < float(duration) <= 2.5)


def load_records(path: str | Path) -> list[dict[str, Any]]:
    """Load either a JSON list or JSONL manifest."""
    manifest = Path(path)
    if not manifest.is_file():
        raise FileNotFoundError(manifest)
    text = manifest.read_text(encoding="utf-8").strip()
    if not text:
        return []
    if text.startswith("["):
        records = json.loads(text)
    else:
        records = [json.loads(line) for line in text.splitlines() if line.strip()]
    if not isinstance(records, list) or not all(isinstance(record, dict) for record in records):
        raise ValueError(f"manifest must contain JSON objects: {manifest}")
    return records


def load_gold_ids(path: str | Path | None) -> set[str]:
    if not path:
        return set()
    exclusions: set[str] = set()
    for record in load_records(path):
        row_id = str(record.get("id") or "").strip()
        if row_id:
            exclusions.add(row_id)
        if record.get("audio_path"):
            exclusions.add(f"audio:{Path(str(record['audio_path'])).resolve()}")
    return exclusions


def _resolved_audio_path(value: str, manifest_path: str | Path) -> str:
    path = Path(str(value or ""))
    if not path.is_absolute():
        path = Path(manifest_path).parent / path
    return str(path.resolve())


def load_external_manifest(
    path: str | Path,
    *,
    expected_source: str,
    split: str = "train",
    gold_ids: set[str] | None = None,
) -> list[dict[str, Any]]:
    """Validate a prepared source manifest and return trainer-ready rows."""
    rows: list[dict[str, Any]] = []
    excluded = gold_ids or set()
    for index, record in enumerate(load_records(path)):
        row_id = str(record.get("id") or f"{expected_source}-{index}").strip()
        if row_id in excluded:
            continue
        if str(record.get("split") or "train").lower() != split:
            continue
        source = str(record.get("source") or expected_source).strip()
        if source != expected_source:
            raise ValueError(f"{path}: row {row_id} source={source!r}, expected {expected_source!r}")
        transcript = " ".join(str(record.get("transcript") or "").split())
        if not transcript:
            raise ValueError(f"{path}: row {row_id} has no transcript")
        audio_path = _resolved_audio_path(str(record.get("audio_path") or ""), path)
        if f"audio:{audio_path}" in excluded:
            continue
        if not Path(audio_path).is_file():
            raise FileNotFoundError(f"{path}: row {row_id} audio not found: {audio_path}")
        license_name = str(record.get("license") or "").strip()
        if not license_name:
            raise ValueError(f"{path}: row {row_id} is missing license provenance")
        if source == "sabi_corrected":
            if record.get("consent_for_model_training") is not True:
                raise ValueError(f"{path}: Sabi row {row_id} lacks explicit model-training consent")
            if str(record.get("review_status") or "").lower() not in {"approved", "reviewed"}:
                raise ValueError(f"{path}: Sabi row {row_id} lacks human transcript approval")
        duration = float(record.get("duration") or 0.0)
        if duration <= 0:
            try:
                import soundfile as sf

                duration = float(sf.info(audio_path).duration)
            except Exception:
                duration = 0.0
        if duration and not 0.2 <= duration <= 30.0:
            LOGGER.warning("Skipping external row %s with duration %.2fs", row_id, duration)
            continue
        rows.append(
            {
                "id": row_id,
                "audio": audio_path,
                "transcript": transcript,
                "source": source,
                "license": license_name,
                "speaker_id": str(record.get("speaker_id") or ""),
                "duration": duration,
                "is_short_response": bool(
                    record.get("is_short_response", is_short_response(transcript, duration))
                ),
                "consent_for_model_training": record.get("consent_for_model_training"),
            }
        )
    return rows


def _weighted_sample_with_cap(
    rows: list[dict[str, Any]],
    count: int,
    *,
    rng: random.Random,
    repeat_cap: int,
) -> list[dict[str, Any]]:
    if count <= 0 or not rows:
        return []
    allowed = min(int(count), len(rows) * max(1, int(repeat_cap)))
    pool = list(rows)
    selected: list[dict[str, Any]] = []
    uses: Counter[str] = Counter()
    while len(selected) < allowed:
        candidates = [
            row for row in pool
            if uses[str(row.get("id") or row.get("audio"))] < repeat_cap
        ]
        if not candidates:
            break
        weights = [4.0 if row.get("is_short_response") else 1.0 for row in candidates]
        row = rng.choices(candidates, weights=weights, k=1)[0]
        selected.append(dict(row))
        uses[str(row.get("id") or row.get("audio"))] += 1
    return selected


def mix_training_rows(
    afrispeech_rows: list[dict[str, Any]],
    external_rows: dict[str, list[dict[str, Any]]],
    *,
    source_ratios: dict[str, float] | None = None,
    seed: int = 20260713,
    repeat_cap: int = 12,
) -> list[dict[str, Any]]:
    """Mix sources while holding general-English retention at 10–20 percent.

    Ratios are targets, not permission to repeat a tiny private corpus forever:
    each external clip is capped at ``repeat_cap`` appearances per epoch.
    """
    ratios = dict(source_ratios or DEFAULT_SOURCE_RATIOS)
    ratio_total = sum(ratios.values())
    if ratio_total <= 0 or ratio_total >= 0.9:
        raise ValueError(f"external source ratios must sum between 0 and 0.9, got {ratio_total}")
    retention = float(ratios.get("general_english_retention", 0.0))
    if not 0.10 <= retention <= 0.20:
        raise ValueError(f"general English retention must be 10–20%, got {retention:.1%}")

    rng = random.Random(seed)
    base = [dict(row) for row in afrispeech_rows]
    target_total = max(len(base), round(len(base) / (1.0 - ratio_total)))
    mixed = list(base)
    for source, ratio in ratios.items():
        quota = round(target_total * float(ratio))
        selected = _weighted_sample_with_cap(
            external_rows.get(source, []),
            quota,
            rng=rng,
            repeat_cap=repeat_cap,
        )
        mixed.extend(selected)
        LOGGER.info(
            "Mixed source %s: %d/%d target samples from %d unique clips",
            source,
            len(selected),
            quota,
            len(external_rows.get(source, [])),
        )
    rng.shuffle(mixed)
    return mixed


def validate_source_mix(
    rows: Iterable[dict[str, Any]],
    *,
    allow_noncommercial: bool,
    require_sources: Iterable[str] = (),
) -> dict[str, Any]:
    """Return a provenance ledger or fail on unsafe/missing training data."""
    materialized = list(rows)
    counts = Counter(str(row.get("source") or "unknown") for row in materialized)
    licenses = Counter(str(row.get("license") or "unknown") for row in materialized)
    missing = [source for source in require_sources if counts[source] == 0]
    if missing:
        raise RuntimeError(f"required training sources missing: {', '.join(missing)}")

    noncommercial = sorted(
        license_name
        for license_name in licenses
        if any(marker in license_name.upper() for marker in NONCOMMERCIAL_MARKERS)
    )
    if noncommercial and not allow_noncommercial:
        raise RuntimeError(
            "noncommercial data present; this run cannot produce a deployable paid-product model: "
            + ", ".join(noncommercial)
        )
    return {
        "total": len(materialized),
        "sources": dict(sorted(counts.items())),
        "licenses": dict(sorted(licenses.items())),
        "contains_noncommercial_data": bool(noncommercial),
        "commercial_deployment_eligible": not noncommercial,
    }


def write_jsonl(path: str | Path, rows: Iterable[dict[str, Any]]) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
