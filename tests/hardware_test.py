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
    print("\n✅ STATUS: Environment is ready to build Milestone 1!")
else:
    print("\n❌ STATUS: CUDA is NOT detected. Check NVIDIA Linux drivers.")
print("===========================================")
