"""Download the optional local translator; weights stay outside Git."""
from pathlib import Path


def main():
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        raise SystemExit("Install optional dependencies: python -m pip install -r requirements-ai.txt")
    destination = Path(__file__).resolve().parent / ".local_models/kazRush-ru-kk"
    snapshot_download(repo_id="deepvk/kazRush-ru-kk", local_dir=str(destination))
    print(f"Local translator ready: {destination}")


if __name__ == "__main__":
    main()
