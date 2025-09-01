import ffmpeg
from typing import Literal, Optional
from fastapi import UploadFile
import logging
import tempfile
import os

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("convertion_api")
UMASK_PERMS = os.umask(0o777)

QUALITY_MAP = {
    "low": 8,
    "medium": 5,
    "high": 2,
    "best": 0,
}


QUALITY_OPTIONS = Literal["low", "medium", "high", "best"]


async def diskConvertMp3(
    file: UploadFile, quality: QUALITY_OPTIONS = "best"
) -> Optional[bytes]:
    """
    Converts an uploaded audio/video file to MP3 format using disk storage.
    Refactor reason: less memory overhead, more stable and less prone to corruption during conversion.

    Args:
        file: UploadFile
        quality: ('low', 'medium', 'high', 'best').

    Returns:
        The converted MP3 data as bytes, or None if conversion fails.
    """
    quality_level = quality.lower()
    q_value = QUALITY_MAP.get(quality_level, QUALITY_MAP["best"])

    suffix = os.path.splitext(file.filename)[1] or ""
    input_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=suffix)
    os.chmod(input_temp_file.name, 0o777)
    output_temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3")
    os.chmod(output_temp_file.name, 0o777)
    try:
        await file.seek(0)
        input_data = await file.read()
        if not input_data:
            print("No data read from input file")
            return None
        input_temp_file.write(input_data)
        input_temp_file.close()

        ffmpeg.input(input_temp_file.name).output(
            output_temp_file.name,
            format="mp3",
            acodec="libmp3lame",
            **{"q:a": q_value}
        ).run(quiet=True, overwrite_output=True)

        output_temp_file.close()

        with open(output_temp_file.name, "rb") as f:
            converted_data = f.read()

        if not converted_data:
            print("FFmpeg produced empty output")
            return None

        return converted_data

    except ffmpeg.Error as e:
        error_message = e.stderr.decode(
            "utf-8", errors="ignore") if e.stderr else str(e)
        print(f"FFmpeg error: {error_message}")
        return None

    except Exception as e:
        print(f"An unexpected error occurred during conversion: {e}")
        return None

    finally:
        try:
            os.unlink(input_temp_file.name)
            os.unlink(output_temp_file.name)
        except Exception as cleanup_error:
            print(f"Error cleaning up temporary files: {cleanup_error}")
