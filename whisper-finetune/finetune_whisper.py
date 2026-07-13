#!/usr/bin/env python3
"""
Fine-tune Whisper large-v3 on AfriSpeech-200 (Nigerian-accented English).
Uses LoRA (Low-Rank Adaptation) for memory-efficient training.

Target hardware: NVIDIA RTX 4000 SFF Ada (20GB VRAM), 62GB RAM
Expected duration: 4-8 hours
Output: CTranslate2 model ready for faster-whisper

Dataset: AfriSpeech-200 by Intron Health (Nigerian English subset)
  - ~45K samples of Nigerian-accented English
  - 82 accent groups, 120+ speakers
  - Clinical + general domain
  - CC BY-NC-SA 4.0
"""

import os
import sys
import time
import logging
import subprocess
import random
from dataclasses import dataclass
from typing import Any, Dict, List
from pathlib import Path

import torch

# ─── Configuration ───────────────────────────────────────────────
MODEL_NAME = os.getenv("SABI_FINETUNE_MODEL", "openai/whisper-small")
DATASET_REPO = "intronhealth/afrispeech-200"
DATA_DIR = "/opt/sabi/whisper-finetune/data/afrispeech-200"

RUN_NAME = os.getenv(
    "SABI_FINETUNE_RUN_NAME",
    f"{MODEL_NAME.rsplit('/', 1)[-1]}-ng-english-telephony-v1",
)
OUTPUT_ROOT = "/opt/sabi/whisper-finetune/output"
OUTPUT_DIR = f"{OUTPUT_ROOT}/{RUN_NAME}/lora"
MERGED_DIR = f"{OUTPUT_ROOT}/{RUN_NAME}/merged"
CT2_OUTPUT_DIR = f"{OUTPUT_ROOT}/{RUN_NAME}/ct2"
FINAL_MODEL_DIR = f"/opt/sabi/sabi-server/models/{RUN_NAME}-ct2"

# Training hyperparameters — optimized for RTX 4000 (20GB VRAM)
PER_DEVICE_BATCH_SIZE = int(os.getenv("SABI_FINETUNE_BATCH_SIZE", "2"))
GRADIENT_ACCUMULATION_STEPS = int(os.getenv("SABI_FINETUNE_GRAD_ACCUM", "8"))
LEARNING_RATE = float(os.getenv("SABI_FINETUNE_LEARNING_RATE", "1e-4"))
WARMUP_RATIO = 0.05
NUM_TRAIN_EPOCHS = float(os.getenv("SABI_FINETUNE_EPOCHS", "1"))
EVAL_STEPS = 500
SAVE_STEPS = 500
LOGGING_STEPS = 25
MAX_INPUT_LENGTH = 30.0  # seconds

# LoRA configuration
LORA_R = 32          # Rank — higher = more capacity, more memory
LORA_ALPHA = 64      # Scaling factor (typically 2x rank)
LORA_DROPOUT = 0.05  # Regularization

COUNTRY_FILTER = "NG"  # Only Nigerian-accented English
TELEPHONY_AUGMENT_PROBABILITY = float(os.getenv("SABI_TELEPHONY_AUGMENT_PROB", "0.65"))
MAX_TRAIN_SAMPLES = int(os.getenv("SABI_FINETUNE_MAX_TRAIN_SAMPLES", "0"))
MAX_EVAL_SAMPLES = int(os.getenv("SABI_FINETUNE_MAX_EVAL_SAMPLES", "0"))
EXPORT_FINAL_MODEL = os.getenv("SABI_FINETUNE_EXPORT_FINAL", "0").lower() in {
    "1", "true", "yes", "on"
}

# ─── Logging Setup ───────────────────────────────────────────────
log_dir = Path("/opt/sabi/whisper-finetune/logs")
log_dir.mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(log_dir / "training.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
logger = logging.getLogger("whisper-finetune")


# ─── On-the-fly Data Collator ───────────────────────────────────
@dataclass
class LazyAudioCollator:
    """
    Loads audio files, extracts mel features, and tokenizes transcripts
    on-the-fly during training. Only keeps batch_size samples in memory.
    """
    processor: Any
    decoder_start_token_id: int

    @staticmethod
    def _telephony_augment(audio_array, sr: int):
        """Approximate Sabi's 8 kHz phone channel without changing the label."""
        import numpy as np
        import librosa

        audio = np.asarray(audio_array, dtype=np.float32)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        if sr != 16000:
            audio = librosa.resample(audio, orig_sr=sr, target_sr=16000)

        narrowband = librosa.resample(audio, orig_sr=16000, target_sr=8000)
        # G.711-style companding plus quantization, then return to Whisper's 16 kHz input.
        mu = 255.0
        peak = max(float(np.max(np.abs(narrowband))), 1e-6)
        normalized = np.clip(narrowband / peak, -1.0, 1.0)
        compressed = np.sign(normalized) * np.log1p(mu * np.abs(normalized)) / np.log1p(mu)
        quantized = np.round((compressed + 1.0) * 127.5) / 127.5 - 1.0
        expanded = np.sign(quantized) * np.expm1(np.abs(quantized) * np.log1p(mu)) / mu

        # Mild varying SNR teaches robustness without burying every training example.
        signal_rms = max(float(np.sqrt(np.mean(expanded ** 2))), 1e-5)
        snr_db = random.uniform(10.0, 28.0)
        noise_rms = signal_rms / (10 ** (snr_db / 20.0))
        noisy = expanded + np.random.normal(0.0, noise_rms, expanded.shape).astype(np.float32)
        gain = random.uniform(0.65, 1.15)
        noisy = np.clip(noisy * gain, -1.0, 1.0)
        return librosa.resample(noisy, orig_sr=8000, target_sr=16000).astype(np.float32)

    def __call__(self, features: List[Dict[str, Any]]) -> Dict[str, torch.Tensor]:
        import soundfile as sf
        import librosa

        input_features_list = []
        labels_list = []

        for feature in features:
            audio_array, sr = sf.read(feature["audio_path"])
            if random.random() < TELEPHONY_AUGMENT_PROBABILITY:
                audio_array = self._telephony_augment(audio_array, sr)
                sr = 16000
            elif sr != 16000:
                audio_array = librosa.resample(
                    audio_array, orig_sr=sr, target_sr=16000
                )

            mel = self.processor.feature_extractor(
                audio_array, sampling_rate=16000
            ).input_features[0]
            input_features_list.append({"input_features": mel})

            labels = self.processor.tokenizer(feature["transcript"]).input_ids
            labels_list.append({"input_ids": labels})

        batch = self.processor.feature_extractor.pad(
            input_features_list, return_tensors="pt"
        )

        labels_batch = self.processor.tokenizer.pad(
            labels_list, return_tensors="pt"
        )

        labels = labels_batch["input_ids"].masked_fill(
            labels_batch.attention_mask.ne(1), -100
        )

        if (labels[:, 0] == self.decoder_start_token_id).all().cpu().item():
            labels = labels[:, 1:]

        batch["labels"] = labels
        return batch


def main():
    start_time = time.time()

    logger.info("=" * 70)
    logger.info("  Whisper Fine-tuning on AfriSpeech-200")
    logger.info("  Nigerian-accented English — LoRA Fine-tuning")
    logger.info("=" * 70)
    logger.info(f"GPU: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
    if torch.cuda.is_available():
        vram = torch.cuda.get_device_properties(0).total_memory / 1e9
        logger.info(f"VRAM: {vram:.1f} GB")
    logger.info(f"Model: {MODEL_NAME}")
    logger.info(f"LoRA: r={LORA_R}, alpha={LORA_ALPHA}, dropout={LORA_DROPOUT}")
    logger.info(f"Effective batch size: {PER_DEVICE_BATCH_SIZE * GRADIENT_ACCUMULATION_STEPS}")
    logger.info(f"Learning rate: {LEARNING_RATE}")
    logger.info(f"Epochs: {NUM_TRAIN_EPOCHS}")
    logger.info(f"Telephony augmentation probability: {TELEPHONY_AUGMENT_PROBABILITY:.0%}")
    logger.info(f"Run: {RUN_NAME}")
    logger.info("")

    # ─── Imports ───
    import csv
    import tarfile
    from datasets import Dataset, DatasetDict
    from huggingface_hub import hf_hub_download, list_repo_tree
    from transformers import (
        WhisperForConditionalGeneration,
        WhisperProcessor,
        Seq2SeqTrainingArguments,
        Seq2SeqTrainer,
    )
    from peft import LoraConfig, get_peft_model, PeftModel
    import evaluate

    # ─── Load Processor ───
    logger.info("Loading Whisper processor...")
    processor = WhisperProcessor.from_pretrained(
        MODEL_NAME, language="english", task="transcribe"
    )

    # ─── Load Dataset ───
    logger.info(f"Loading AfriSpeech-200 from {DATASET_REPO}...")
    os.makedirs(DATA_DIR, exist_ok=True)

    accent_dirs = list(list_repo_tree(
        DATASET_REPO, path_in_repo="transcripts", repo_type="dataset"
    ))
    accents = [getattr(d, "path", str(d)).split("/")[-1] for d in accent_dirs]
    logger.info(f"Found {len(accents)} accent groups")

    all_data = {"train": [], "dev": [], "test": []}
    skipped_audio = 0
    found_audio = 0

    for accent_idx, accent in enumerate(accents):
        logger.info(f"  [{accent_idx+1}/{len(accents)}] Processing accent: {accent}")

        for split in ["train", "dev", "test"]:
            csv_filename = f"transcripts/{accent}/{split}.csv"
            try:
                csv_path = hf_hub_download(
                    repo_id=DATASET_REPO,
                    filename=csv_filename,
                    repo_type="dataset",
                    local_dir=DATA_DIR,
                )
            except Exception:
                continue

            extract_dir = os.path.join(DATA_DIR, "audio_extracted", accent, split)
            extracted_marker = os.path.join(extract_dir, ".extracted")

            if not os.path.exists(extracted_marker):
                os.makedirs(extract_dir, exist_ok=True)
                try:
                    tar_items = list(list_repo_tree(
                        DATASET_REPO,
                        path_in_repo=f"audio/{accent}/{split}",
                        repo_type="dataset",
                    ))
                except Exception:
                    continue

                for tar_info in tar_items:
                    tar_path = getattr(tar_info, "path", str(tar_info))
                    if not tar_path.endswith(".tar.gz"):
                        continue
                    try:
                        local_tar = hf_hub_download(
                            repo_id=DATASET_REPO,
                            filename=tar_path,
                            repo_type="dataset",
                            local_dir=DATA_DIR,
                        )
                        with tarfile.open(local_tar, "r:gz") as tar:
                            tar.extractall(extract_dir)
                    except Exception as e:
                        logger.warning(f"    Failed: {tar_path}: {e}")
                        continue

                open(extracted_marker, "w").close()

            # Hash-based audio file matching
            import glob as _glob
            wav_index = {}
            for wav_path in _glob.glob(
                os.path.join(extract_dir, "**/*.wav"), recursive=True
            ):
                wav_index[os.path.basename(wav_path)] = wav_path

            with open(csv_path, encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    if COUNTRY_FILTER and row.get("country") != COUNTRY_FILTER:
                        continue

                    audio_basename = os.path.basename(
                        row.get("audio_paths", "")
                    )
                    audio_full = wav_index.get(audio_basename)

                    if not audio_full:
                        skipped_audio += 1
                        continue

                    duration = float(row.get("duration", "0"))
                    if duration > MAX_INPUT_LENGTH or duration < 0.5:
                        continue

                    found_audio += 1
                    all_data[split].append({
                        "audio": audio_full,
                        "transcript": row["transcript"],
                    })

    logger.info(f"Dataset complete: {found_audio} found, {skipped_audio} skipped")
    for split, rows in all_data.items():
        logger.info(f"  {split}: {len(rows)} samples")

    if not all_data["train"]:
        raise RuntimeError("No training samples found!")

    # Build DatasetDict (just file paths — audio loaded on-the-fly)
    logger.info("Building DatasetDict (lazy audio loading)...")
    dataset = DatasetDict()
    for split, rows in all_data.items():
        if rows:
            limit = MAX_TRAIN_SAMPLES if split == "train" else MAX_EVAL_SAMPLES
            if limit and len(rows) > limit:
                random.Random(20260713 + len(split)).shuffle(rows)
                rows = rows[:limit]
            dataset[split] = Dataset.from_dict({
                "audio_path": [r["audio"] for r in rows],
                "transcript": [r["transcript"] for r in rows],
            })

    train_split = "train"
    eval_split = "dev" if "dev" in dataset else "test"
    logger.info(f"  Train: {len(dataset[train_split])}, Eval: {len(dataset[eval_split])}")

    # ─── Load Model with LoRA ───
    logger.info(f"Loading {MODEL_NAME}...")
    model = WhisperForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
    )

    model.generation_config.language = "english"
    model.generation_config.task = "transcribe"
    model.generation_config.forced_decoder_ids = None
    model.config.use_cache = False

    # Apply LoRA
    logger.info("Applying LoRA adapters...")
    lora_config = LoraConfig(
        r=LORA_R,
        lora_alpha=LORA_ALPHA,
        lora_dropout=LORA_DROPOUT,
        target_modules=[
            "q_proj", "v_proj", "k_proj", "out_proj",
            "fc1", "fc2",
        ],
        bias="none",
        task_type="SEQ_2_SEQ_LM",
    )
    model = get_peft_model(model, lora_config)

    trainable = sum(p.numel() for p in model.parameters() if p.requires_grad)
    total = sum(p.numel() for p in model.parameters())
    logger.info(f"  Total: {total/1e6:.0f}M, Trainable: {trainable/1e6:.1f}M ({100*trainable/total:.2f}%)")

    # ─── Evaluation ───
    wer_metric = evaluate.load("wer")

    def compute_metrics(pred):
        pred_ids = pred.predictions
        label_ids = pred.label_ids
        label_ids[label_ids == -100] = processor.tokenizer.pad_token_id
        pred_str = processor.tokenizer.batch_decode(pred_ids, skip_special_tokens=True)
        label_str = processor.tokenizer.batch_decode(label_ids, skip_special_tokens=True)
        wer = 100 * wer_metric.compute(predictions=pred_str, references=label_str)
        return {"wer": wer}

    # ─── Collator & Training Args ───
    data_collator = LazyAudioCollator(
        processor=processor,
        decoder_start_token_id=model.config.decoder_start_token_id,
    )

    logger.info("Configuring training...")
    training_args = Seq2SeqTrainingArguments(
        output_dir=OUTPUT_DIR,
        per_device_train_batch_size=PER_DEVICE_BATCH_SIZE,
        gradient_accumulation_steps=GRADIENT_ACCUMULATION_STEPS,
        learning_rate=LEARNING_RATE,
        warmup_ratio=WARMUP_RATIO,
        num_train_epochs=NUM_TRAIN_EPOCHS,
        gradient_checkpointing=True,
        fp16=True,
        eval_strategy="steps",
        eval_steps=EVAL_STEPS,
        save_steps=SAVE_STEPS,
        logging_steps=LOGGING_STEPS,
        generation_max_length=225,
        predict_with_generate=True,
        report_to=["tensorboard"],
        push_to_hub=False,
        load_best_model_at_end=True,
        metric_for_best_model="wer",
        greater_is_better=False,
        save_total_limit=3,
        dataloader_num_workers=0,
        dataloader_pin_memory=True,
        optim="adamw_torch",  # Standard AdamW — LoRA params are tiny
        remove_unused_columns=False,
    )

    trainer = Seq2SeqTrainer(
        args=training_args,
        model=model,
        train_dataset=dataset[train_split],
        eval_dataset=dataset[eval_split],
        data_collator=data_collator,
        compute_metrics=compute_metrics,
        processing_class=processor.feature_extractor,
    )

    # ─── Train ───
    logger.info("=" * 70)
    logger.info("  STARTING TRAINING (LoRA)")
    logger.info("=" * 70)

    train_result = trainer.train()

    logger.info("Training complete!")
    logger.info(f"  Loss: {train_result.training_loss:.4f}")
    logger.info(f"  Time: {train_result.metrics.get('train_runtime', 0)/3600:.1f} hours")

    # ─── Save LoRA model ───
    logger.info(f"Saving LoRA model to {OUTPUT_DIR}...")
    trainer.save_model(OUTPUT_DIR)
    processor.save_pretrained(OUTPUT_DIR)

    # ─── Final Evaluation ───
    logger.info("Final evaluation...")
    test_split = "test" if "test" in dataset else eval_split
    if test_split in dataset and test_split != eval_split:
        results = trainer.evaluate(dataset[test_split])
        logger.info(f"  Test WER: {results.get('eval_wer', 'N/A'):.2f}%")
    else:
        results = trainer.evaluate()
        logger.info(f"  Eval WER: {results.get('eval_wer', 'N/A'):.2f}%")

    # ─── Merge LoRA into base model ───
    logger.info("Merging LoRA weights into base model...")
    del model
    del trainer
    torch.cuda.empty_cache()
    import gc
    gc.collect()

    base_model = WhisperForConditionalGeneration.from_pretrained(
        MODEL_NAME,
        torch_dtype=torch.float16,
        low_cpu_mem_usage=True,
    )
    merged_model = PeftModel.from_pretrained(base_model, OUTPUT_DIR)
    merged_model = merged_model.merge_and_unload()

    logger.info(f"Saving merged model to {MERGED_DIR}...")
    os.makedirs(MERGED_DIR, exist_ok=True)
    merged_model.save_pretrained(MERGED_DIR)
    processor.save_pretrained(MERGED_DIR)

    del merged_model
    del base_model
    torch.cuda.empty_cache()
    gc.collect()

    # ─── Convert to CTranslate2 ───
    logger.info(f"Converting to CTranslate2...")
    try:
        result = subprocess.run(
            [
                "ct2-whisper-converter",
                "--model", MERGED_DIR,
                "--output_dir", CT2_OUTPUT_DIR,
                "--quantization", "float16",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        logger.info("CTranslate2 conversion successful!")
    except subprocess.CalledProcessError as e:
        logger.error(f"CTranslate2 conversion failed: {e.stderr}")
        sys.exit(1)

    # ─── Deploy ───
    if EXPORT_FINAL_MODEL:
        logger.info(f"Exporting candidate to {FINAL_MODEL_DIR}...")
        os.makedirs(FINAL_MODEL_DIR, exist_ok=True)
        subprocess.run(
            ["cp", "-r", f"{CT2_OUTPUT_DIR}/.", FINAL_MODEL_DIR],
            check=True,
        )
    else:
        logger.info("Candidate export disabled; production remains unchanged pending gold-set evaluation.")

    total_time = time.time() - start_time
    logger.info("")
    logger.info("=" * 70)
    logger.info("  TRAINING COMPLETE!")
    logger.info("=" * 70)
    logger.info(f"  Total time: {total_time/3600:.1f} hours")
    logger.info(f"  LoRA model: {OUTPUT_DIR}")
    logger.info(f"  Merged model: {MERGED_DIR}")
    logger.info(f"  CTranslate2: {CT2_OUTPUT_DIR}")
    logger.info(f"  Production export: {FINAL_MODEL_DIR if EXPORT_FINAL_MODEL else 'disabled'}")
    logger.info("=" * 70)


if __name__ == "__main__":
    main()
