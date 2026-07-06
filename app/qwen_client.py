"""
Thin client over Qwen Cloud (DashScope) for the Ad-Variant Factory.

Three capabilities, all first-party Alibaba Cloud:
  - chat()        : text reasoning (brand extraction, angles, scripts) via OpenAI-compatible API
  - chat_json()   : same, but forces a JSON object back
  - critique()    : multimodal — qwen-vl looks at a rendered ad image and scores it (the moat)
  - generate_image(): Tongyi Wanxiang text-to-image (async DashScope ImageSynthesis)
"""
from __future__ import annotations

import base64
import json
import mimetypes
import time
from pathlib import Path
from typing import Any

import dashscope
from dashscope import ImageSynthesis
from openai import OpenAI

from . import config

# Point the OpenAI-compatible client + the dashscope SDK at the intl region.
_client = OpenAI(api_key=config.require_key(), base_url=config.OPENAI_BASE_URL)
dashscope.api_key = config.DASHSCOPE_API_KEY
dashscope.base_http_api_url = config.HTTP_BASE_URL


def chat(messages: list[dict], model: str | None = None, temperature: float = 0.8) -> str:
    """Plain text completion."""
    resp = _client.chat.completions.create(
        model=model or config.TEXT_MODEL,
        messages=messages,
        temperature=temperature,
    )
    return resp.choices[0].message.content or ""


def chat_json(messages: list[dict], model: str | None = None, temperature: float = 0.7) -> Any:
    """Completion constrained to a single JSON object."""
    resp = _client.chat.completions.create(
        model=model or config.PLAN_MODEL,
        messages=messages,
        temperature=temperature,
        response_format={"type": "json_object"},
    )
    return json.loads(resp.choices[0].message.content or "{}")


def embed(texts: list[str], model: str | None = None) -> list[list[float]]:
    """Embed a batch of texts (text-embedding-v3) for semantic memory recall."""
    resp = _client.embeddings.create(model=model or config.EMBED_MODEL, input=texts)
    return [d.embedding for d in resp.data]


def _img_to_data_url(image_path: str | Path) -> str:
    p = Path(image_path)
    mime = mimetypes.guess_type(p.name)[0] or "image/png"
    b64 = base64.b64encode(p.read_bytes()).decode()
    return f"data:{mime};base64,{b64}"


def critique(image_path: str | Path, instruction: str, model: str | None = None) -> str:
    """Show qwen-vl an image + an instruction; return its raw text judgement."""
    resp = _client.chat.completions.create(
        model=model or config.VL_MODEL,
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": _img_to_data_url(image_path)}},
                    {"type": "text", "text": instruction},
                ],
            }
        ],
        temperature=0.2,
    )
    return resp.choices[0].message.content or ""


def generate_image(
    prompt: str,
    out_path: str | Path,
    size: str = "1024*1024",
    negative_prompt: str = "",
    model: str | None = None,
    timeout: int = 180,
) -> Path:
    """
    Tongyi Wanxiang text-to-image. Synchronous wrapper over the async job.
    `size` uses Wanxiang's WxH format with a '*' separator, e.g. '1024*1024', '720*1280'.
    """
    rsp = ImageSynthesis.call(
        model=model or config.WANX_T2I_MODEL,
        prompt=prompt,
        negative_prompt=negative_prompt or None,
        n=1,
        size=size,
    )
    if rsp.status_code != 200:
        raise RuntimeError(f"Wanxiang error {rsp.status_code}: {rsp.code} {rsp.message}")

    url = rsp.output.results[0].url
    import requests

    deadline = time.time() + timeout
    while True:
        r = requests.get(url, timeout=60)
        if r.status_code == 200:
            break
        if time.time() > deadline:
            raise RuntimeError(f"Timed out downloading generated image: {url}")
        time.sleep(2)

    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_bytes(r.content)
    return out
