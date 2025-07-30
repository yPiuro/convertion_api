from dataclasses import dataclass
from typing import Literal
from fastapi import HTTPException
import os
import json
import time
import shutil
import stat

BASE_DIR = os.getcwd()
UMASK_PERMS = os.umask(0o777)

@dataclass
class CachedFile:
    filename: str
    video_file_hash: str
    expiry_date: int
    file_bytes: bytes
    file_ext: str


async def find_file(video_file_hash: str, ext: Literal['mp3', 'video']) -> CachedFile:
    cache_folder = f"{os.getcwd()}/cache/{video_file_hash}"
    if os.path.exists(cache_folder) and len(os.listdir(cache_folder)) == 3:
        with open(f"{cache_folder}/metadata.json") as meta_file:
            meta = json.load(meta_file)
        if meta["expiry_date"] < time.time():
            shutil.rmtree(cache_folder)
            raise HTTPException(
                410, "Sorry this file was cached but has just been invalidated, please upload it again :)")
        filename = f"{meta['filename']}.{ext}" if ext == 'mp3' else meta['filename'] + meta['file_ext']
        with open(f"{cache_folder}/{filename}", "rb") as f_file:
            return CachedFile(filename=meta['filename'], video_file_hash=video_file_hash, expiry_date=meta["expiry_date"], file_bytes=f_file.read(), file_ext=meta['file_ext'])
    else:
        return None


def view_info() -> list[CachedFile]:
    cache_folder = f"{os.getcwd()}/cache"
    cached_data = []
    for folder in os.listdir(cache_folder):
        try:
            if len(os.listdir(f'{cache_folder}/{folder}')) > 3:
                continue

            with open(f"{cache_folder}/{folder}/metadata.json") as meta_file:
                meta = json.load(meta_file)

            for f in os.listdir(f"{cache_folder}/{folder}"):
                if f.endswith("json"):
                    continue
                with open(f"{cache_folder}/{folder}/{f}", 'rb') as f_file:
                    cached_data.append(CachedFile(filename=f.split('.')[
                        0], video_file_hash=folder, expiry_date=meta["expiry_date"], file_bytes=b'0', file_ext=meta['file_ext']))
                break
        except Exception as e:
            if type(e) == PermissionError:
                print("Permission error on file? Could be due to being on a un-privileged user or different user as the one who created the files.\nFull Exception:")
                print(e)
            print(type(e))
            return view_info()
    return cached_data


async def cache_file(video_file_hash: str, filename: str, file_bytes: bytes, converted_file_bytes: bytes):
    """Store original MP4 bytes, converted MP3 bytes, and expiry in the cache folder."""
    subdir = os.path.join(BASE_DIR, f"cache/{video_file_hash}")
    os.makedirs(subdir, exist_ok=True)
    expiry_date = time.time() + (3600//2//3)
    video_path = os.path.join(subdir, filename)
    with open(video_path, "wb") as f:
        f.write(file_bytes)
    os.chmod(video_path, 0o664)
    base, _ = os.path.splitext(filename)
    mp3_filename = base + ".mp3"
    mp3_path = os.path.join(subdir, mp3_filename)
    with open(mp3_path, "wb") as f:
        f.write(converted_file_bytes)
    os.chmod(mp3_path, 0o664)

    metadata = {
        "expiry_date": expiry_date,
        "filename": base,
        "file_ext": _,
    }
    meta_path = os.path.join(subdir, "metadata.json")
    with open(meta_path, "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)
    os.chmod(meta_path, 0o664)
    return CachedFile(
        filename=filename,
        video_file_hash=video_file_hash,
        expiry_date=expiry_date,
        file_bytes=converted_file_bytes,
        file_ext=_
    )


def expiry_job():
    cache_folder = f"{os.getcwd()}/cache"
    if os.path.exists(cache_folder):
        for folder in os.listdir(cache_folder):
            with open(f"{cache_folder}/{folder}/metadata.json") as meta_file:
                meta = json.load(meta_file)
            if meta["expiry_date"] is not None and meta["expiry_date"] < time.time():
                os.chmod(f"{cache_folder}/{folder}", stat.S_IWRITE)
                shutil.rmtree(f"{cache_folder}/{folder}")
