"""App module that includes API definition."""

import os
import io
from fastapi import FastAPI, HTTPException, status, UploadFile, File, BackgroundTasks, Request, Header, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from typing import Any
import util
import hashlib
from util import schemas, ffmpegHelper
import util.cache
import time
import asyncio
import queue
import logging
import base64
import cv2

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("convertion_api")

SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv",
                              ".avi", ".mov", ".wmv", ".flv", ".webm"}

DESCRIPTION = """
Video conversion API helps you convert your legally acquired videos to mp3.

Features:
- Upload and convert files (/convert)
- Download files (/cache)
"""

TAGS = [
    {"name": "convert", "description": "Operations with file conversion."},
    {"name": "cache", "description": "Download or view cached files."},
]

app = FastAPI(
    title="Open Convert API",
    description=DESCRIPTION,
    summary="API for converting video files to mp3 using ffmpeg.",
    version="0.0.1",
    contact={"name": "yPiuro", "url": "https://nohello.net/",
             "email": "y@piuro.lol"},
    license_info={"name": "GNU GPL 3.0",
                  "url": "https://www.gnu.org/licenses/gpl-3.0.en.html"},
    openapi_tags=TAGS,
    docs_url="/",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

stop_event = asyncio.Event()
cached_data: list[util.schemas.CachedFileInfo] = None
cached_data_q: "queue.Queue[Any]" = queue.Queue()


async def consume_cache(q: queue.Queue):
    """Consume cache data and update global state."""
    global cached_data
    while not stop_event.is_set():
        try:
            cached_data = q.get_nowait()
        except queue.Empty:
            pass
        await asyncio.sleep(0.5)


async def produce_cache(q: queue.Queue):
    """Produce fresh cache data and enqueue it."""
    while not stop_event.is_set():
        q.put(util.cache.view_info())
        await asyncio.sleep(0.5)


async def expiry_loop():
    """Purge stale files periodically."""
    while not stop_event.is_set():
        util.cache.expiry_job()
        await asyncio.sleep(0.25)


async def valid_content_length(content_length: int = Header(..., lt=20_000_000)):
    """Validate uploaded file size."""
    if content_length >= 20_000_000:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, detail="Content too large")
    return content_length


@app.on_event("startup")
async def startup_tasks():
    """Start background tasks for cache management."""
    app.state.expiry_task = asyncio.create_task(expiry_loop())
    app.state.producer_task = asyncio.create_task(produce_cache(cached_data_q))
    app.state.consumer_task = asyncio.create_task(consume_cache(cached_data_q))


@app.on_event("shutdown")
async def shutdown_tasks():
    """Stop background tasks gracefully."""
    stop_event.set()
    for task in (app.state.producer_task, app.state.consumer_task, app.state.expiry_task):
        task.cancel()
    await asyncio.gather(app.state.producer_task, app.state.consumer_task, app.state.expiry_task, return_exceptions=True)


@app.post("/convert/", tags=["convert"], status_code=status.HTTP_200_OK, dependencies=[Depends(valid_content_length)])
async def convert_file(background_tasks: BackgroundTasks, file: UploadFile = File(...), quality: ffmpegHelper.QUALITY_OPTIONS = "best"):
    """Convert uploaded video file to mp3."""
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="No filename provided")

    file_extension = os.path.splitext(file.filename)[1].lower()
    if file_extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unsupported format '{file_extension}'")

    file_ogname = file.filename
    hasher = hashlib.sha256()
    chunk = await file.read()
    hasher.update(chunk)
    file_hash = hasher.hexdigest()

    cached_file = await util.cache.find_file(file_hash, "mp3")
    if cached_file:
        return StreamingResponse(
            content=io.BytesIO(cached_file.file_bytes),
            media_type="audio/mpeg",
            headers={
                "Content-Disposition": f"attachment; filename={os.path.splitext(file_ogname)[0]}.mp3",
                "Content-Length": str(len(cached_file.file_bytes)),
            },
        )

    await file.seek(0)
    try:
        converted_file = await ffmpegHelper.diskConvertMp3(file, quality)
    except Exception as e:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR, f"Conversion error: {e}")

    if not converted_file:
        raise HTTPException(status.HTTP_500_INTERNAL_SERVER_ERROR,
                            "Conversion produced empty output")

    await file.seek(0)
    background_tasks.add_task(util.cache.cache_file, file_hash, file_ogname, await file.read(), converted_file)

    return StreamingResponse(
        content=io.BytesIO(converted_file),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"attachment; filename={os.path.splitext(file_ogname)[0]}.mp3",
            "Content-Length": str(len(converted_file)),
        },
    )


@app.get("/cache/dl/{file_id}", tags=["cache"], name="dl_mp3")
async def download_converted_cached_file(file_id: str):
    """Download converted cached file."""
    cached_file = await util.cache.find_file(file_id, "mp3")
    if not cached_file or not cached_file.file_bytes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid")
    return StreamingResponse(
        content=io.BytesIO(cached_file.file_bytes),
        media_type="audio/mpeg",
        headers={
            "Content-Disposition": f"attachment; filename={cached_file.filename}.mp3",
            "Content-Length": str(len(cached_file.file_bytes)),
        },
    )


@app.get("/cache/dl/og/{file_id}", tags=["cache"], name="dl_video")
async def download_original_cached_file(file_id: str):
    """Download original cached file."""
    cached_file = await util.cache.find_file(file_id, "video")
    if not cached_file or not cached_file.file_bytes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid")
    return StreamingResponse(
        content=io.BytesIO(cached_file.file_bytes),
        media_type="video",
        headers={
            "Content-Disposition": f"attachment; filename={cached_file.filename}{cached_file.file_ext}",
            "Content-Length": str(len(cached_file.file_bytes)),
        },
    )


def generate_thumbnail(video_path: str) -> str:
    """
    Generate a thumbnail for the given video file and return it as a base64-encoded string.
    """
    try:
        video = cv2.VideoCapture(video_path)
        if not video.isOpened():
            logger.info(f"Failed to open video file: {video_path}")
            return None

        success, frame = video.read()
        video.release()

        if not success:
            logger.info(
                f"Failed to read the first frame of video: {video_path}")
            return None

        _, buffer = cv2.imencode(".jpg", frame)

        thumbnail_base64 = base64.b64encode(buffer).decode("utf-8")
        return thumbnail_base64
    except Exception as e:
        logger.info(f"Failed to generate thumbnail for {video_path}: {e}")
        return None


@app.get("/cache/", tags=["cache"], response_model=schemas.CacheResponse, responses={status.HTTP_404_NOT_FOUND: {"model": schemas.CacheNotFoundMessage}})
async def view_cache(request: Request):
    """Retrieve cached files."""
    pretty_cached_data = {}
    for file in cached_data:
        og_url = f"{request.base_url}cache/dl/og/{file.video_file_hash}"
        mp3_url = f"{request.base_url}cache/dl/{file.video_file_hash}"
        time_invalidate = time.strftime(
            "%H:%M:%S", time.localtime(file.expiry_date))
        min_till_expire = max(
            round((file.expiry_date - time.time()) / 60, 2), 0)
        logger.info(file.filename)
        video_file_path = f"{os.getcwd().replace("\\", "/")}/cache/{file.video_file_hash}/{file.filename}{file.file_ext}"
        thumbnail_base64 = generate_thumbnail(video_file_path)

        pretty_cached_data[file.filename] = schemas.CachedFileInfo(
            minutes_until_invalid=min_till_expire,
            time_invalidate=time_invalidate,
            link_converted=mp3_url,
            link_original=og_url,
            thumbnail=thumbnail_base64,
            file_extension=file.file_ext
        )
    if not cached_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No cached files found")

    return schemas.CacheResponse(message="Currently cached files", files=pretty_cached_data)
