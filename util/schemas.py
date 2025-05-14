from typing import Dict, Any
from datetime import datetime
from pydantic import BaseModel, AnyUrl, RootModel


class CachedFileInfo(BaseModel):
    """
    Schema for detailed information about a single cached file.
    """
    link_original: str
    link_converted: str
    time_invalidate: str
    minutes_until_invalid: float


class CachedFiles(RootModel[Dict[str, CachedFileInfo]]):
    """
    Schema representing a dictionary of cached files,
    where keys are filenames and values are CachedFileInfo objects.
    """
    pass

    model_config = {
        "json_schema_extra": {
            "examples": [
                {
                    "filename1.mp4": {
                        "link_original": "cache/dl/og/9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
                        "link_converted": "cache/dl/9f86d081884c7d659a2feaa0c55ad015a3bf4f1b2b0b822cd15d6c15b0f00a08",
                        "time_invalidate": "14:20:30",
                        "minutes_until_invalid": 24
                    }
                },
                {
                    "another_file.mov": {
                        "link_original": "cache/dl/og/60303ae22b998861bce3b28f33eec1be758a213c86c93c076dbe9f558c11c752",
                        "link_converted": "cache/dl/60303ae22b998861bce3b28f33eec1be758a213c86c93c076dbe9f558c11c752",
                        "time_invalidate": "14:20:30",
                        "minutes_until_invalid": 22
                    }
                }
            ]
        }
    }


class CacheResponse(BaseModel):
    """
    Overall response schema for retrieving cached files. (200)
    """
    message: str
    files: CachedFiles


class CacheNotFoundMessage(BaseModel):
    """
    Schema for the response when no cached files are found (404).
    """
    detail: str


class FileConversionSuccessResponse(BaseModel):
    """
    Schema for the response when a file has been successfully converted. (200)
    """
    message: str
    file_link: AnyUrl
