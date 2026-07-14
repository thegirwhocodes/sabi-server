# Sabi Nigerian-English STT training

This pipeline trains a candidate only. It never promotes a model automatically.

## Required data mix

- Nigerian AfriSpeech (`CC-BY-NC-SA-4.0`): research-only until commercial permission is obtained.
- Official Mozilla Common Voice English export, filtered to Nigerian accent metadata (`CC0-1.0`).
- Human-corrected Sabi call turns with explicit model-training consent. Ordinary recording consent is not sufficient.
- LibriSpeech general English (`CC-BY-4.0`) held to a 10–20% target so Nigerian adaptation does not erase broader English.
- Licensed real noise under `data/noise/{market,generator,chatter,television,baby,connection}`.

The seven private gold clips remain evaluation-only. `prepare_external_manifests.py` and `training_data.py` exclude their resolved audio paths.

## Prepare manifests

```bash
python prepare_external_manifests.py \
  --output-dir /opt/sabi/whisper-finetune/manifests \
  --common-voice-root /opt/sabi/whisper-finetune/data/common-voice-en \
  --librispeech-root /opt/sabi/whisper-finetune/data/LibriSpeech/train-clean-100 \
  --sabi-root /shared/audio \
  --gold-manifest /opt/sabi/whisper-finetune/gold_manifest_private.json
```

The Common Voice argument must point to an official export containing `validated.tsv` and `clips/`. The script accepts only rows whose accent/country/locale metadata says Nigerian or `en-NG`.

## Run a complete research candidate

```bash
export SABI_FINETUNE_COMMON_VOICE_MANIFEST=/opt/sabi/whisper-finetune/manifests/nigerian_common_voice.jsonl
export SABI_FINETUNE_SABI_MANIFEST=/opt/sabi/whisper-finetune/manifests/sabi_corrected.jsonl
export SABI_FINETUNE_RETENTION_MANIFEST=/opt/sabi/whisper-finetune/manifests/general_english_retention.jsonl
export SABI_FINETUNE_GOLD_MANIFEST=/opt/sabi/whisper-finetune/gold_manifest_private.json
export SABI_FINETUNE_NOISE_ROOT=/opt/sabi/whisper-finetune/data/noise
export SABI_FINETUNE_REQUIRE_ALL_SOURCES=1
export SABI_FINETUNE_ALLOW_NONCOMMERCIAL=1
export SABI_FINETUNE_EXPORT_FINAL=0
bash run_training.sh
```

Setting `SABI_FINETUNE_ALLOW_NONCOMMERCIAL=1` marks the resulting provenance ledger as ineligible for commercial deployment; it does not waive AfriSpeech's license. A paid-product candidate must omit AfriSpeech or have documented commercial permission.

## Augmentation

The collator applies:

- 300–3400 Hz telephone band limiting;
- exact G.711 PCMA (80%) and PCMU (20%) round trips;
- real noise at 3–24 dB SNR, with a synthetic fallback for incomplete research runs;
- 20 ms AudioSocket framing, pre-roll, trailing silence, packet loss, and gain variation;
- stronger coverage and capped oversampling for short names, numbers, and one-word responses.

## Denoising evaluation

DeepFilterNet v3 is installed but production remains off by default:

```bash
python evaluate_gold.py gold_manifest_private.json \
  --model base=small \
  --model candidate=/path/to/candidate/ct2 \
  --audio-variant raw \
  --audio-variant deepfilternet \
  --device cuda \
  --output gold_results.json
```

Only set `SABI_STT_DENOISE=1` after cleaned audio improves the held-out results without regressing any name, number, or short phonics clip. The runtime cleaner is fail-open and can be disabled without changing code.
