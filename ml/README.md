# OKOA AI — Machine Learning Pipeline (`ml/`)

This directory contains data curation, prompt engineering, fine-tuning scripts, and safety evaluation suites for OKOA AI's conversational agent (Phase 4).

## Architecture

- **Base Model:** Meta Llama 3 8B Instruct (`meta-llama/Meta-Llama-3-8B-Instruct`)
- **Adaptation Strategy:** Single-GPU QLoRA (4-bit quantization, LoRA rank $r=16$, $\alpha=32$) on AWS EC2 `g5.xlarge` (24GB A10G)
- **Target Domains:** Swahili, Sheng, and Kenyan English localized empathetic CBT companion
- **Safety Envelope:** The model **only** processes Safe and Distressed messages (Crisis score $>85\%$ is intercepted upstream by the risk pre-screening gate)

## Directory Structure

```
ml/
├── data/
│   ├── README.md                          # Data curation & anonymization standards
│   └── sample_conversations_sw_sheng.jsonl# Seed training conversations
├── prompts/
│   ├── system_prompt_en.txt               # English CBT guardrailed system prompt
│   ├── system_prompt_sw.txt               # Swahili CBT guardrailed system prompt
│   ├── system_prompt_sheng.txt            # Sheng CBT guardrailed system prompt
│   └── redteam_eval_suite.jsonl           # Adversarial safety & guardrail test suite
├── training/
│   ├── requirements.txt                   # PyTorch & HuggingFace training dependencies
│   └── train_qlora.py                     # Single-GPU QLoRA SFT training script
└── eval/
    └── evaluate_model.py                  # Red-team automated eval harness & report generator
```

## Quickstart

### 1. Environment Setup
```bash
python -m venv .venv
source .venv/bin/activate  # or .venv\Scripts\activate on Windows
pip install -r ml/training/requirements.txt
```

### 2. Fine-Tuning (QLoRA)
```bash
python ml/training/train_qlora.py \
  --model_id meta-llama/Meta-Llama-3-8B-Instruct \
  --data_path ml/data/sample_conversations_sw_sheng.jsonl \
  --output_dir ml/checkpoints/okoa-llama3-adapter
```

### 3. Safety & Guardrail Evaluation
```bash
python ml/eval/evaluate_model.py \
  --adapter_path ml/checkpoints/okoa-llama3-adapter \
  --suite_path ml/prompts/redteam_eval_suite.jsonl
```
