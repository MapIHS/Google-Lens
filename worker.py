#!/usr/bin/env python3
"""Authenticated HTTP wrapper for the persistent Google Lens browser."""

import asyncio
import hmac
import json
import logging
import os
import signal
import sys
import tempfile
import warnings
from contextlib import asynccontextmanager
from io import BytesIO
from pathlib import Path
from typing import Literal

from fastapi import FastAPI, Header, HTTPException, Request
from PIL import Image, UnidentifiedImageError

MAX_BYTES = 10 * 1024 * 1024
MAX_PIXELS = 20_000_000
SCRAPER_TIMEOUT_SECONDS = 170
SCRAPER = Path(__file__).with_name("google_lens_scraper.py")
FORMATS = {"JPEG": ".jpg", "PNG": ".png", "WEBP": ".webp"}
REQUEST_LOCK = asyncio.Lock()
logger = logging.getLogger("google_lens_worker")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if not os.environ.get("GOOGLE_LENS_WORKER_TOKEN"):
        raise RuntimeError("GOOGLE_LENS_WORKER_TOKEN must be configured")
    Path(os.environ.get("GOOGLE_LENS_PROFILE_DIR", "/profile")).mkdir(parents=True, exist_ok=True)
    yield


app = FastAPI(title="Google Lens Worker", docs_url=None, redoc_url=None, lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


def verify_authorization(value: str | None) -> None:
    token = os.environ.get("GOOGLE_LENS_WORKER_TOKEN", "")
    expected = f"Bearer {token}"
    if not token or not value or not hmac.compare_digest(value, expected):
        raise HTTPException(status_code=401, detail="Unauthorized")


async def read_image(request: Request) -> tuple[bytes, str]:
    content_type = request.headers.get("content-type", "").split(";", 1)[0].strip().lower()
    if content_type not in ("image/jpeg", "image/png", "image/webp"):
        raise HTTPException(status_code=415, detail="Content-Type must be JPEG, PNG, or WebP")

    content_length = request.headers.get("content-length")
    if content_length and content_length.isdigit() and int(content_length) > MAX_BYTES:
        raise HTTPException(status_code=413, detail="Image size exceeds 10 MiB")

    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > MAX_BYTES:
            raise HTTPException(status_code=413, detail="Image size exceeds 10 MiB")
    if not body:
        raise HTTPException(status_code=400, detail="Image request body is required")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            image = Image.open(BytesIO(body))
            image_format = image.format or ""
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=422, detail="Invalid or oversized image") from None

    expected_format = {"image/jpeg": "JPEG", "image/png": "PNG", "image/webp": "WEBP"}[content_type]
    if image_format != expected_format:
        raise HTTPException(status_code=422, detail="Image content does not match Content-Type")
    if width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise HTTPException(status_code=422, detail="Image resolution exceeds 20 megapixels")
    return bytes(body), FORMATS[image_format]


@app.post("/api/google-lens")
async def google_lens(
    request: Request,
    mode: Literal["ai", "visual"] = "visual",
    authorization: str | None = Header(default=None),
) -> dict[str, object]:
    verify_authorization(authorization)
    body, extension = await read_image(request)

    async with REQUEST_LOCK:
        image_path: str | None = None
        try:
            with tempfile.NamedTemporaryFile(prefix="google-lens-", suffix=extension, delete=False) as image_file:
                image_file.write(body)
                image_path = image_file.name

            process = await asyncio.create_subprocess_exec(
                sys.executable,
                str(SCRAPER),
                image_path,
                "--mode",
                mode,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                start_new_session=True,
            )
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=SCRAPER_TIMEOUT_SECONDS
                )
            except asyncio.TimeoutError:
                try:
                    os.killpg(process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                await process.wait()
                logger.warning("lens_scraper_failed mode=%s reason=timeout", mode)
                raise HTTPException(status_code=504, detail="Google Lens search timed out") from None

            if process.returncode != 0:
                message = stderr.decode("utf-8", errors="replace")[-1000:].lower()
                if any(word in message for word in ("captcha", "verifikasi", "recaptcha", "sorry")):
                    logger.warning("lens_scraper_failed mode=%s exit_code=%s reason=verification_required", mode, process.returncode)
                    raise HTTPException(status_code=503, detail="Google Lens requires additional verification")
                logger.warning("lens_scraper_failed mode=%s exit_code=%s reason=browser_error", mode, process.returncode)
                raise HTTPException(status_code=502, detail="Google Lens search failed")

            try:
                result = json.loads(stdout)
            except (json.JSONDecodeError, UnicodeDecodeError):
                logger.warning("lens_scraper_failed mode=%s reason=invalid_json", mode)
                raise HTTPException(status_code=502, detail="Google Lens returned an invalid response") from None
            if not isinstance(result, dict) or result.get("mode") != mode:
                logger.warning("lens_scraper_failed mode=%s reason=invalid_result", mode)
                raise HTTPException(status_code=502, detail="Google Lens returned an invalid response")
            return {"status": "success", "data": result}
        finally:
            if image_path:
                Path(image_path).unlink(missing_ok=True)
