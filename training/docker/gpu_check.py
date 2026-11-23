"""Check that PyTorch in the training container sees the AMD GPU and can run a kernel."""

from __future__ import annotations

import sys

import torch


def main() -> int:
    print(f"torch {torch.__version__}, HIP {torch.version.hip}")
    if not torch.cuda.is_available():  # ROCm builds expose the GPU through the torch.cuda API
        print("no GPU visible to PyTorch")
        return 1
    print(f"device: {torch.cuda.get_device_name(0)}, bf16: {torch.cuda.is_bf16_supported()}")
    a = torch.randn(2048, 2048, device="cuda")
    b = a @ a.T
    torch.cuda.synchronize()
    print(f"matmul ok, checksum {float(b.trace()):.1f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
