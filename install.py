"""Auto-detect GPU and install correct dependencies."""

import subprocess
import sys
import os


def has_nvidia_gpu() -> bool:
    """Check if NVIDIA GPU is available by running nvidia-smi."""
    try:
        output = subprocess.run(
            ["nvidia-smi", "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return output.returncode == 0 and output.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired, Exception):
        return False


def main() -> None:
    print("=" * 70)
    print("flow-st8 Setup — Auto-detecção de GPU")
    print("=" * 70)

    print("\n1️⃣  Detectando placa de vídeo NVIDIA...")
    has_gpu = has_nvidia_gpu()

    if has_gpu:
        print("   ✅ GPU NVIDIA detectada!")
        gpu_info = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader"],
            capture_output=True,
            text=True,
        )
        if gpu_info.stdout:
            print(f"   {gpu_info.stdout.strip()}")
        print("\n2️⃣  Instalando dependências com CUDA (torch CUDA 12.8)...")
        print("   ⏳ Isso pode levar 5-10 minutos (~2.7GB)...\n")
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "pip",
                "install",
                "-r",
                "requirements.txt",
                "torch",
                "--index-url",
                "https://download.pytorch.org/whl/cu128",
            ]
        )
        if result.returncode != 0:
            print("\n❌ Erro ao instalar dependências!")
            return
    else:
        print(
            "   ❌ GPU NVIDIA não detectada. Instalando versão CPU (mais rápido)."
        )
        print("   ℹ️  Modelos grandes (medium/large-v3-turbo) serão lentos em CPU.")
        print("   💡 Considere usar 'base' ou 'small' para melhor experiência.\n")
        print("2️⃣  Instalando dependências sem CUDA (torch CPU)...")
        print("   ⏳ Isso leva 2-3 minutos...\n")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "-r", "requirements.txt", "torch"]
        )
        if result.returncode != 0:
            print("\n❌ Erro ao instalar dependências!")
            return

    print("\n" + "=" * 70)
    print("✅ Setup completo!")
    print("=" * 70)
    print("\nPróximos passos:\n")
    print("1. Abra o arquivo flow-st8.vbs (ou rode: python main.py)")
    print("2. Um ícone de microfone aparecerá na bandeja do sistema")
    print("3. Aperte Ctrl+Win para começar a gravar")
    print("4. Na primeira execução, o modelo Whisper será baixado (~1.5GB)\n")

    if not has_gpu:
        print("💡 Dica: Como você não tem GPU, recomendamos alterar o modelo em:")
        print(f"   {os.path.expandvars('%APPDATA%')}/flow-st8/config.toml")
        print("   Mude: name = 'large-v3-turbo'")
        print("   Para: name = 'base'  (ou 'small' para melhor qualidade)\n")


if __name__ == "__main__":
    main()
