"""
Smoke test for Qwen Cloud access. Run BEFORE building anything else.

    python -m scripts.hello_qwen          # text only
    python -m scripts.hello_qwen --image  # also test Wanxiang image gen

Proves: the DashScope key works on the intl endpoint, the OpenAI-compatible
chat API responds, and (optionally) Tongyi Wanxiang text-to-image returns a file.
"""
import sys
from pathlib import Path

# allow running as `python scripts/hello_qwen.py` too
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app import config, qwen_client  # noqa: E402


def main() -> None:
    print(f"Endpoint: {config.OPENAI_BASE_URL}")
    print(f"Text model: {config.TEXT_MODEL}\n")

    reply = qwen_client.chat(
        [{"role": "user", "content": "Reply with exactly: Qwen Cloud is wired up."}],
        temperature=0,
    )
    print("CHAT  ->", reply.strip())

    if "--image" in sys.argv:
        print(f"\nImage model: {config.WANX_T2I_MODEL}  (this can take ~20-40s)")
        out = qwen_client.generate_image(
            "a clean studio product photo of a matte black water bottle on a "
            "soft gradient background, commercial advertising lighting",
            out_path="output/_smoke.png",
        )
        print("IMAGE ->", out.resolve())

    print("\nOK.")


if __name__ == "__main__":
    main()
