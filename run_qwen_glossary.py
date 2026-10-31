#!/usr/bin/env python3
"""Start the local Kazakh model, draft translations, then stop the model server."""

from __future__ import annotations

import argparse
import socket
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

from qwen_glossary_proposals import generate


ROOT = Path(__file__).resolve().parent
DEFAULT_MODEL = ROOT / ".local_models/qwen35-kazakh/Qwen3.5-4B-Kazakh.Q4_K_M.gguf"
DEFAULT_SERVER = ROOT / ".local_models/llama-cpu/llama-server.exe"
DEFAULT_ENGLISH = ROOT / "Исходники/grand-loc-qa-handout-2026-10-27/handout/intl_en.arb"


def available_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


def run(corrections: Path, english: Path, glossary: Path, output: Path,
        model: Path = DEFAULT_MODEL, server_bin: Path = DEFAULT_SERVER,
        include_drafts: bool = False, limit: int | None = None) -> tuple[int, int]:
    for path in (corrections, english, glossary, model, server_bin):
        if not path.is_file():
            raise FileNotFoundError(path)
    port = available_port()
    url = f"http://127.0.0.1:{port}"
    command = [str(server_bin), "-m", str(model), "--host", "127.0.0.1",
               "--port", str(port), "-c", "2048", "-t", "8", "--reasoning", "off"]
    log_path = ROOT / ".artifact_runtime/qwen_server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("wb") as log:
        flags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        process = subprocess.Popen(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT,
                                   creationflags=flags)
        try:
            deadline = time.monotonic() + 120
            while time.monotonic() < deadline:
                if process.poll() is not None:
                    raise RuntimeError(f"Model server exited early; see {log_path}")
                try:
                    with urllib.request.urlopen(url + "/health", timeout=2) as response:
                        if response.status == 200:
                            break
                except Exception:
                    time.sleep(1)
            else:
                raise TimeoutError(f"Model server did not become ready; see {log_path}")
            return generate(corrections, english, glossary, output, url, include_drafts, limit)
        finally:
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--corrections", type=Path, default=ROOT / "corrections.csv")
    parser.add_argument("--english-arb", type=Path, default=DEFAULT_ENGLISH)
    parser.add_argument("--glossary", type=Path, default=ROOT / "private/game_glossary_candidates.csv")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--model", type=Path, default=DEFAULT_MODEL)
    parser.add_argument("--server-bin", type=Path, default=DEFAULT_SERVER)
    parser.add_argument("--include-drafts", action="store_true")
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    rows, valid = run(args.corrections, args.english_arb, args.glossary, args.out,
                      args.model, args.server_bin, args.include_drafts, args.limit)
    print(f"Saved {valid}/{rows} structurally valid, unverified translations to {args.out}")


if __name__ == "__main__":
    main()
