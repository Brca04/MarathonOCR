#!/usr/bin/env python3
"""Verify the GPU stack before trusting any benchmark number.

The RTX 5070 is Blackwell, compute capability **sm_120**. Default PyTorch
wheels are not built for it and fail at the first kernel launch with

    CUDA error: no kernel image is available for execution on the device

which is easy to misread as a driver problem. The fix is the cu128 build:

    pip install torch torchvision --index-url https://download.pytorch.org/whl/cu128

Run this first. If it does not print a green line for torch, every timing you
measure afterwards is CPU timing.
"""

from __future__ import annotations

import importlib
import sys

OK, WARN, BAD = "\033[32m  ok \033[0m", "\033[33mwarn \033[0m", "\033[31mFAIL \033[0m"

OPTIONAL = [
    ("ultralytics", "detection (YOLO)"),
    ("easyocr", "recognizer: easyocr"),
    ("paddleocr", "recognizer: paddleocr"),
    ("transformers", "recognizer: trocr"),
    ("anthropic", "recognizer: vlm"),
]


def check_torch() -> bool:
    try:
        import torch
    except ImportError:
        print(f"{BAD} torch not installed")
        return False

    print(f"{OK} torch {torch.__version__} (CUDA build: {torch.version.cuda})")

    if not torch.cuda.is_available():
        print(f"{BAD} torch.cuda.is_available() is False - running on CPU")
        return False

    name = torch.cuda.get_device_name(0)
    cap = torch.cuda.get_device_capability(0)
    print(f"{OK} device: {name}  compute capability sm_{cap[0]}{cap[1]}")

    arch_list = getattr(torch.cuda, "get_arch_list", lambda: [])()
    target = f"sm_{cap[0]}{cap[1]}"
    if arch_list and target not in arch_list:
        print(f"{BAD} this torch build supports {arch_list}")
        print(f"       it does NOT support {target} - your GPU will not be used.")
        print("       pip install torch torchvision --index-url "
              "https://download.pytorch.org/whl/cu128")
        return False

    # A real kernel launch is the only honest test; capability checks pass on
    # builds that still cannot execute.
    try:
        a = torch.randn(512, 512, device="cuda")
        torch.mm(a, a).sum().item()
        torch.cuda.synchronize()
        print(f"{OK} matmul on GPU succeeded")
    except Exception as exc:  # noqa: BLE001
        print(f"{BAD} GPU kernel launch failed: {exc}")
        return False

    free, total = torch.cuda.mem_get_info()
    print(f"{OK} VRAM {free / 1e9:.1f} GB free of {total / 1e9:.1f} GB")
    return True


def main() -> int:
    print(f"python {sys.version.split()[0]}\n")
    healthy = check_torch()

    print()
    for module, purpose in OPTIONAL:
        try:
            m = importlib.import_module(module)
            version = getattr(m, "__version__", "?")
            print(f"{OK} {module:<14} {version:<12} {purpose}")
        except ImportError:
            print(f"{WARN} {module:<14} {'-':<12} {purpose} (not installed)")

    print()
    if healthy:
        print("GPU stack looks good.")
    else:
        print("GPU unavailable - benchmarks will run on CPU and timings are "
              "not representative.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
