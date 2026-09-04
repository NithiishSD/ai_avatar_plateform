import torch
import sys

print("===========================================")
print("  AI AVATAR PLATFORM - STEP 0 VERIFICATION  ")
print("===========================================")
print(f"Python Location : {sys.executable}")
print(f"PyTorch Version : {torch.__version__}")
print(f"CUDA Available  : {torch.cuda.is_available()}")

if torch.cuda.is_available():
    print(f"GPU Model       : {torch.cuda.get_device_name(0)}")
    vram_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
    print(f"Dedicated VRAM  : {vram_gb:.2f} GB")
    print("\n✅ STATUS: Environment is ready with NVIDIA GPU hardware acceleration (CUDA enabled)!")
else:
    print("\nℹ️  STATUS: No NVIDIA GPU detected. Platform will run in CPU fallback mode.")
    print("✅ STATUS: Environment is ready with CPU execution!")
print("===========================================")
