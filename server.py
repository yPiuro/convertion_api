"""App module that includes API definition."""

import os
import io
from fastapi import FastAPI, HTTPException, status, UploadFile, File, BackgroundTasks, Request
from fastapi.responses import StreamingResponse
from typing import Any
import util
import hashlib
from util import schemas, ffmpegHelper
import util.cache
import time
import asyncio
import queue

# Define the set of supported video extensions
SUPPORTED_VIDEO_EXTENSIONS = {".mp4", ".mkv",
                              ".avi", ".mov", ".wmv", ".flv", ".webm"}

#######################################################################################################

DESCRIPTION = """
# Video conversion API helps you do convert your definetly legally aquired videos to mp3. 🚀

## Files

You can **upload and then convert files** (/convert).\n
You can **download files** (_not implemented_).\n
\n
This API will include some basic caching and cache validation if I can get around to it.
"""

TAGS = [
    {
        "name": "convert",
        "description": "Operations with file convertion. (A bit of Cache logic will be here)",
    },
    {
        "name": "cache",
        "description": "Download or view currently cached files",
    },
]

app = FastAPI(
    title="Open Convert API",
    description=DESCRIPTION,
    summary="Simple API that uses ffmpeg to convert video files to mp3",
    version="0.0.1",
    contact={
        "name": "yPiuro",
        "url": "https://nohello.net/",
        "email": "y@piuro.lol",
    },
    license_info={
        "name": "GNU GPL 3.0",
        "url": "https://www.gnu.org/licenses/gpl-3.0.en.html",
    },
    openapi_tags=TAGS,
    docs_url="/"
)

# This is the Fast API initiation which includes license info, api info, contact info and etc

stop_event = asyncio.Event()


# shared state and queue, using a global.
cached_data: Any = None
cached_data_q: "queue.Queue[Any]" = queue.Queue()


async def consume_cache(q: queue.Queue):
    global cached_data
    while not stop_event.is_set():
        try:
            item = q.get_nowait()
            cached_data = item
        except queue.Empty:
            pass
        await asyncio.sleep(.5)


async def produce_cache(q: queue.Queue):
    while not stop_event.is_set():
        fresh = util.cache.view_info()
        q.put(fresh)
        await asyncio.sleep(.5)


async def expiry_loop():
    """Purge stale files every 0.25s."""
    while not stop_event.is_set():
        util.cache.expiry_job()
        await asyncio.sleep(.25)


@app.on_event("startup")
async def startup_tasks():
    # start all background loops and stash the tasks so we can cancel them
    app.state.expiry_task = asyncio.create_task(expiry_loop())
    app.state.producer_task = asyncio.create_task(
        produce_cache(cached_data_q)
    )
    app.state.consumer_task = asyncio.create_task(
        consume_cache(cached_data_q)
    )


@app.on_event("shutdown")
async def shutdown_tasks():
    stop_event.set()
    # cancel the running tasks
    for t in (app.state.producer_task, app.state.consumer_task,
              app.state.expiry_task):
        t.cancel()
    await asyncio.gather(
        app.state.producer_task,
        app.state.consumer_task,
        app.state.expiry_task,
        return_exceptions=True
    )

# This is just to spawn repeating jobs e.g making a cache in memory instead of grabbing cache everytime a request to /cache is made.

#######################################################################################################


@app.post(
    "/convert/",
    tags=['convert'],
    # response_model=schemas.FileConversionSuccessResponse,
    status_code=status.HTTP_200_OK
)
async def convert_file(background_tasks: BackgroundTasks, file: UploadFile = File(...), quality: ffmpegHelper.QUALITY_OPTIONS = 'best'):
    """
    Uploads and validates a video file for conversion.

    Args:
        file (UploadFile): The video file to be uploaded.
    """
    # Handle cases where filename might be None or not have an extension
    if file.filename is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="No filename provided in the upload."
        )

    file_extension = os.path.splitext(file.filename)[1].lower()
    # Validate the file extension to make sure ffmpeg supports it
    if file_extension not in SUPPORTED_VIDEO_EXTENSIONS:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST,
                            detail=f"Unsupported file format '{file_extension}'. Supported extensions: {', '.join(SUPPORTED_VIDEO_EXTENSIONS)}")

    file_ogname = file.filename
    hasher = hashlib.sha256()
    try:
        chunck = await file.read()
        hasher.update(chunck)
    except Exception as e:
        raise HTTPException(
            400, f"Invalid file, couldn't generate sha256: {e}")

    file_hash = hasher.hexdigest()

    # Checks for cache, this also always invalidates a cache if the time has passed (cache job hasn't been called yet or it broke etc) this will be the last resort to invalidate cache.
    cached_file = await util.cache.find_file(file_hash, 'mp3')

    if cached_file:
        return StreamingResponse(content=io.BytesIO(cached_file.file_bytes), media_type='audio/mpeg', headers={'Content-Disposition': f'attachment; filename={os.path.splitext(file_ogname)[0]}.mp3', 'Content-Lenght': str(len(cached_file.file_bytes))}) if cached_file is not None else None
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid file")

    await file.seek(0)
    converted_file = await ffmpegHelper.memConvertMp3(file, quality)
    if converted_file is None:
        raise HTTPException(500, "Could not convert")
    await file.seek(0)
    background_tasks.add_task(util.cache.cache_file, file_hash, file_ogname, await file.read(), converted_file)
    return StreamingResponse(content=io.BytesIO(converted_file), media_type='audio/mpeg', headers={'Content-Disposition': f'attachment; filename={os.path.splitext(file_ogname)[0]}.mp3', 'Content-Lenght': str(len(converted_file))})


@app.get("/cache/dl/{file_id}", tags=["cache"], name='dl_mp3')
async def donwload_converted_cached_file(file_id: str):
    """
    Initiates the download of a converted cached file.

    Args:
        file_id (str): The ID of the cached file to download.
    """
    cached_file = await util.cache.find_file(file_id, 'mp3')
    if not cached_file or not cached_file.file_bytes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid")
    return StreamingResponse(content=io.BytesIO(cached_file.file_bytes), media_type='audio/mpeg', headers={'Content-Disposition': f'attachment; filename={cached_file.filename}', 'Content-Lenght': str(len(cached_file.file_bytes))})


@app.get("/cache/dl/og/{file_id}", tags=["cache"], name='dl_mp4')
async def donwload_original_cached_file(file_id: str):
    """
    Initiates the download of an original cached file.

    Args:
        file_id (str): The ID of the cached file to download.
    """
    cached_file = await util.cache.find_file(file_id, 'mp4')
    if not cached_file or not cached_file.file_bytes:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Invalid")
    return StreamingResponse(content=io.BytesIO(cached_file.file_bytes), media_type='video', headers={'Content-Disposition': f'attachment; filename={cached_file.filename}', 'Content-Lenght': str(len(cached_file.file_bytes))})


@app.get("/cache/", tags=['cache'], response_model=schemas.CacheResponse, responses={status.HTTP_404_NOT_FOUND: {"model": schemas.CacheNotFoundMessage}})
async def view_cache(request: Request):
    """
    Retrieves and displays the currently cached files.
    """
    pretty_cached_data = {}
    for file in cached_data:
        og_url = f"{request.base_url}cache/dl/{file.mp4_file_hash}"
        mp3_ulr = f"{request.base_url}cache/dl/og/{file.mp4_file_hash}"
        time_invalidate = time.strftime(
            "%H:%M:%S", time.localtime(file.expiry_date))
        min_till_expire = round((file.expiry_date - time.time())/60, 2)
        min_till_expire = min_till_expire if min_till_expire > 0 else 0
        pretty_cached_data[file.filename] = schemas.CachedFileInfo(
            minutes_until_invalid=min_till_expire, time_invalidate=time_invalidate, link_converted=mp3_ulr, link_original=og_url)
    if not cached_data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="No cached files found")

    return schemas.CacheResponse(message="Currently cached files", files=pretty_cached_data)
