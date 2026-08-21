#!/usr/bin/env python3
"""
Download and prepare a model for TurboLLM from Hugging Face.

Usage:
    python scripts/download_model.py --model neuralmagic/Meta-Llama-3-70B-Instruct-FP8 --output ./models/llama-70b-fp8
"""

import argparse
import json
import os
import sys
from pathlib import Path

from huggingface_hub import snapshot_download, HfApi
from transformers import AutoTokenizer, AutoConfig


def parse_args():
    parser = argparse.ArgumentParser(description="Download and prepare models for TurboLLM inference engine.")
    parser.add_argument(
        "--model", 
        type=str, 
        required=True,
        help="Hugging Face model ID (e.g., neuralmagic/Meta-Llama-3-70B-Instruct-FP8 or meta-llama/Meta-Llama-3-70B-Instruct)"
    )
    parser.add_argument(
        "--output", 
        type=str, 
        default="./models",
        help="Base output directory where the model folder will be created."
    )
    parser.add_argument(
        "--token", 
        type=str, 
        default=os.environ.get("HUGGINGFACE_TOKEN", None),
        help="Hugging Face API token (optional, or set HUGGINGFACE_TOKEN env var for gated models)."
    )
    parser.add_argument(
        "--cache-dir", 
        type=str, 
        default=None,
        help="Optional cache directory for downloaded files."
    )
    return parser.parse_args()


def verify_model_repo(model_id: str, token: str = None):
    """Проверяет существование модели и доступность на HF."""
    try:
        api = HfApi(token=token)
        info = api.model_info(model_id)
        return info
    except Exception as e:
        print(f"❌ Error: Could not fetch model info for '{model_id}': {e}")
        print("   Please check the model name and ensure you have access (if it's a gated model like Llama).")
        sys.exit(1)


def download_model(args):
    # Формируем безопасное и понятное имя папки
    safe_model_name = args.model.replace("/", "_")
    output_dir = Path(args.output) / safe_model_name
    output_dir.mkdir(parents=True, exist_ok=True)

    print(f"🔍 Verifying model '{args.model}' on Hugging Face Hub...")
    model_info = verify_model_repo(args.model, args.token)
    print(f"✅ Model found! Pipeline tag: {getattr(model_info, 'pipeline_tag', 'unknown')}")

    print(f"📥 Downloading all repository files to {output_dir}...")
    try:
        # Скачиваем файлы репозитория напрямую в целевую директорию
        snapshot_download(
            repo_id=args.model,
            cache_dir=args.cache_dir,
            token=args.token,
            local_dir=str(output_dir),
            local_dir_use_symlinks=False,
            resume_download=True
        )
        print(f"✅ Model files successfully downloaded to {output_dir}")
    except Exception as e:
        print(f"❌ Failed to download model files: {e}")
        sys.exit(1)

    # Валидация загруженных конфигураций и токенизатора
    try:
        print("🔧 Validating tokenizer and config...")
        tokenizer = AutoTokenizer.from_pretrained(str(output_dir))
        config = AutoConfig.from_pretrained(str(output_dir))
        
        print(f"   • Model Type: {config.model_type}")
        print(f"   • Hidden Size: {getattr(config, 'hidden_size', 'N/A')}")
        print(f"   • Max Position Embeddings: {getattr(config, 'max_position_embeddings', 'N/A')}")
        print("✅ Config and tokenizer are valid.")
    except Exception as e:
        print(f"⚠️ Warning: Could not fully load tokenizer/config locally: {e}")

    # Проверка формата на предмет FP8
    is_fp8 = "fp8" in args.model.lower()
    
    print("\n" + "="*50)
    print("🎯 Model ready for TurboLLM!")
    print("="*50)
    print(f"   📁 Model path: {output_dir.resolve()}")
    
    if is_fp8:
        print("   ⚡ Status: Detected native FP8 model (ideal for TurboLLM + vLLM).")
        print("      vLLM will load these weights directly with maximum speed and low VRAM.")
    else:
        print("   💡 Status: Standard precision model detected.")
        print("      To apply FP8 quantization at runtime using vLLM, add the flag:")
        print("      --> `--quantization fp8`")

    print("\n   🚀 Example serve command:")
    print(f"      python -m turbollm.serve --model {output_dir.resolve()} --quantization fp8 --kv-cache-dtype fp8 --port 8000")
    print("="*50)


if __name__ == "__main__":
    args = parse_args()
    download_model(args)
