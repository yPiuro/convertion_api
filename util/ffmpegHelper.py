import ffmpeg
import asyncio
from typing import Literal, Optional
from fastapi import UploadFile
import os


QUALITY_MAP = {
    "low": 8,
    "medium": 5,
    "high": 2,
    "best": 0,
}


QUALITY_OPTIONS = Literal["low", "medium", "high", "best"]


async def memConvertMp3(
    file: UploadFile, quality: QUALITY_OPTIONS = "best"
) -> Optional[bytes]:
    """
    Converts an uploaded audio/video file to MP3 format in memory.

    Args:
        file: The FastAPI UploadFile object containing the input media.
        quality: The desired output quality ('low', 'medium', 'high', 'best').

    Returns:
        The converted MP3 data as bytes, or None if conversion fails.
    """
    quality_level = quality.lower()
    if quality_level not in QUALITY_MAP:
        q_value = QUALITY_MAP["best"]
    else:
        q_value = QUALITY_MAP[quality_level]

    try:
        await file.seek(0)
        input_bytes = await file.read()
        process = (
            ffmpeg.input("pipe:0")
            .output(
                "pipe:1",
                format="mp3",
                acodec="libmp3lame",
                **{"q:a": q_value},
            )
            .run_async(
                pipe_stdin=True, pipe_stdout=True, pipe_stderr=True, quiet=True
            )
        )

        stdout_data, stderr_data = await asyncio.to_thread(
            process.communicate, input=input_bytes
        )
        retcode = process.wait()
        if retcode != 0:
            error_message = stderr_data.decode("utf-8", errors="ignore")
            print(
                f"ffmpeg conversion failed (return code {retcode}): {error_message}")
            return None

        return stdout_data

    except ffmpeg.Error as e:
        error_message = e.stderr.decode(
            "utf-8", errors="ignore") if e.stderr else str(e)
        print(f"ffmpeg-python error: {error_message}")
        return None, None
    except Exception as e:
        # Handle any other errors
        print(f"An unexpected error occurred during conversion: {e}")
        return None, None
