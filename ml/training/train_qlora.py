"""Single-GPU QLoRA Fine-Tuning Pipeline for OKOA AI (Phase 4.4).

Fine-tunes Meta-Llama-3-8B-Instruct on Swahili/Sheng mental-health CBT conversations.
Target Hardware: AWS g5.xlarge (1x NVIDIA A10G 24GB VRAM).

Usage:
    python ml/training/train_qlora.py \
        --model_id meta-llama/Meta-Llama-3-8B-Instruct \
        --data_path ml/data/sample_conversations_sw_sheng.jsonl \
        --output_dir ml/checkpoints/okoa-llama3-adapter \
        --num_train_epochs 3
"""
from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("okoa.ml.train")


def parse_args():
    parser = argparse.ArgumentParser(description="OKOA AI QLoRA Fine-Tuning")
    parser.add_argument("--model_id", type=str, default="meta-llama/Meta-Llama-3-8B-Instruct")
    parser.add_argument("--data_path", type=str, default="ml/data/sample_conversations_sw_sheng.jsonl")
    parser.add_argument("--output_dir", type=str, default="ml/checkpoints/okoa-llama3-adapter")
    parser.add_argument("--batch_size", type=int, default=2)
    parser.add_argument("--gradient_accumulation_steps", type=int, default=8)
    parser.add_argument("--learning_rate", type=float, default=2e-4)
    parser.add_argument("--num_train_epochs", type=int, default=3)
    parser.add_argument("--max_seq_length", type=int, default=1024)
    parser.add_argument("--lora_r", type=int, default=16)
    parser.add_argument("--lora_alpha", type=int, default=32)
    parser.add_argument("--lora_dropout", type=float, default=0.05)
    return parser.parse_args()


def load_formatted_dataset(data_path: str):
    """Load JSONL dialogues and format them into HuggingFace Dataset."""
    from datasets import Dataset

    records = []
    with open(data_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                records.append({"messages": item["messages"]})
    logger.info("Loaded %d conversation dialogues from %s", len(records), data_path)
    return Dataset.from_list(records)


def train():
    args = parse_args()
    logger.info("Starting OKOA AI QLoRA training on model=%s", args.model_id)

    try:
        import torch
        from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
        from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig, TrainingArguments
        from trl import SFTTrainer
    except ImportError as e:
        logger.error("Missing ML dependencies. Please run: pip install -r ml/training/requirements.txt (%s)", e)
        return

    # 1. 4-bit Quantization Config (QLoRA)
    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_compute_dtype=torch.bfloat16 if torch.cuda.is_bf16_supported() else torch.float16,
        bnb_4bit_use_double_quant=True,
    )

    # 2. Tokenizer
    tokenizer = AutoTokenizer.from_pretrained(args.model_id, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"

    # 3. Base Model
    device_map = "auto" if torch.cuda.is_available() else None
    model = AutoModelForCausalLM.from_pretrained(
        args.model_id,
        quantization_config=bnb_config if torch.cuda.is_available() else None,
        device_map=device_map,
        torch_dtype=torch.bfloat16 if torch.cuda.is_available() and torch.cuda.is_bf16_supported() else torch.float32,
        trust_remote_code=True,
    )

    if torch.cuda.is_available():
        model = prepare_model_for_kbit_training(model)

    # 4. LoRA Configuration
    peft_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
        bias="none",
        task_type="CAUSAL_LM",
    )

    # 5. Training Arguments
    training_args = TrainingArguments(
        output_dir=args.output_dir,
        num_train_epochs=args.num_train_epochs,
        per_device_train_batch_size=args.batch_size,
        gradient_accumulation_steps=args.gradient_accumulation_steps,
        learning_rate=args.learning_rate,
        lr_scheduler_type="cosine",
        warmup_ratio=0.03,
        logging_steps=10,
        save_strategy="epoch",
        fp16=torch.cuda.is_available() and not torch.cuda.is_bf16_supported(),
        bf16=torch.cuda.is_available() and torch.cuda.is_bf16_supported(),
        report_to="none",
    )

    dataset = load_formatted_dataset(args.data_path)

    # 6. SFT Trainer
    trainer = SFTTrainer(
        model=model,
        train_dataset=dataset,
        peft_config=peft_config,
        dataset_text_field="messages",
        max_seq_length=args.max_seq_length,
        tokenizer=tokenizer,
        args=training_args,
    )

    logger.info("Initiating training loop...")
    trainer.train()

    # 7. Save adapter weights
    Path(args.output_dir).mkdir(parents=True, exist_ok=True)
    trainer.model.save_pretrained(args.output_dir)
    tokenizer.save_pretrained(args.output_dir)
    logger.info("Fine-tuned adapter saved successfully to %s", args.output_dir)


if __name__ == "__main__":
    train()
