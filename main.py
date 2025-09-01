try:
    import uvicorn
    import os
    import shutil
    import platform
    import zipfile
    import tarfile
    import asyncio
    import aiohttp
    import ffmpeg
    import fastapi
    import pydantic
    from util import schemas, ffmpegHelper
    from util import cache
    import util
    from util import COLORS as c
    import server
    import time
except Exception as e:
    print(
        f"""Import error,
    please activate virtual env and pip install requirements.txt: {e}
    If the error above contains 'utill' or 'main'
    redownload the project as there are files missing""")
    exit()

if os.name != 'nt':
    UMASK_PERMS = os.umask(0o777)


async def install_ffmpeg():
    """Attempt to download and extract an ffmpeg binary to the same directory."""
    system = platform.system()
    arch = platform.machine()
    ffmpeg_dir = os.path.dirname(os.getcwd())
    ffmpeg_path = os.path.join(ffmpeg_dir, "ffmpeg") if system != "Windows" else os.path.join(
        ffmpeg_dir, "ffmpeg") + ".exe"

    if os.path.exists(ffmpeg_path) and os.access(ffmpeg_path, os.X_OK):
        return

    download_url = None
    if system == "Windows":
        download_url = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"
    elif system == "Linux":
        if arch == "x86_64":
            download_url = "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz"
        else:
            print(f"Unsupported architecture for Linux: {arch}")
            exit()
    elif system == "Darwin":
        if arch == "x86_64":
            download_url = "https://evermeet.cx/ffmpeg/getrelease"
        elif arch == "arm64":
            download_url = "https://evermeet.cx/ffmpeg/getrelease/arm64"
        else:
            print(f"Unsupported architecture for macOS: {arch}")
            exit()
    else:
        print(f"Unsupported operating system: {system}")
        exit()

    if not download_url:
        print("Could not determine download URL for your system.")
        exit()

    print(f"Downloading from: {download_url}")

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(download_url) as response:
                response.raise_for_status()
                total_size = int(response.headers.get("content-length", 0))
                downloaded_size = 0
                temp_filename = os.path.join(ffmpeg_dir, "ffmpeg_download")

                with open(temp_filename, "wb") as f:
                    async for chunk in response.content.iter_chunked(8192):
                        f.write(chunk)
                        downloaded_size += len(chunk)
                        progress = (downloaded_size / total_size) * 100
                        print(f"Downloaded: {progress:.2f}%", end='\r')
                print("\nDownload complete. Extracting...")

        if system == "Windows":
            with zipfile.ZipFile(temp_filename, 'r') as zip_ref:
                for member in zip_ref.namelist():
                    if member.endswith("ffmpeg.exe"):
                        source = zip_ref.open(member)
                        target = open(ffmpeg_path, "wb")
                        with source, target:
                            shutil.copyfileobj(source, target)
                        break
            extracted_ffmpeg_path = ffmpeg_path
        elif system == "Linux":
            with tarfile.open(temp_filename, 'r:xz') as tar_ref:
                for member in tar_ref.getmembers():
                    if member.isfile() and member.name.endswith("/ffmpeg"):
                        member.name = os.path.basename(member.name)
                        tar_ref.extract(member, path=ffmpeg_dir)
                        break
            extracted_ffmpeg_path = ffmpeg_path
        elif system == "Darwin":
            with tarfile.open(temp_filename, 'r:xz') as tar_ref:
                for member in tar_ref.getmembers():
                    if member.isfile() and "bin/ffmpeg" in member.name:
                        member.name = os.path.basename(member.name)
                        tar_ref.extract(member, path=ffmpeg_dir)
                        break
            extracted_ffmpeg_path = ffmpeg_path

        if system != "Windows" and os.path.exists(extracted_ffmpeg_path):
            os.chmod(extracted_ffmpeg_path, 0o777)

        os.remove(temp_filename)

        if os.path.exists(extracted_ffmpeg_path):
            print(
                f"FFmpeg successfully downloaded and extracted to {extracted_ffmpeg_path}")
        else:
            print(
                "Error: FFmpeg executable not found after extraction. Please install it manually")
            exit()
    except (zipfile.BadZipFile, tarfile.ReadError) as e:
        print(
            f"Error extracting FFmpeg archive: {e} | Please install it manually")
        exit()
    except Exception as e:
        print(
            f"An unexpected error occurred: {e} | Report this @ https://github.com/ypiuro/convertion_api")
        exit()
    return extracted_ffmpeg_path


def setup():
    """
    Check for the 'cache' directory, verifiy FFmpeg installation,
    and load the cache if conditions are met. If ffmpeg is not installed, attempt to install it.
    """
    cache_dir = "cache"

    if not os.path.exists(cache_dir):
        print(f"'{cache_dir}' directory not found. Creating it...")
        try:
            os.makedirs(cache_dir)
            print(f"'{cache_dir}' directory created successfully.")
        except OSError as e:
            print(f"Error creating directory '{cache_dir}': {e}")
            return
    ffmpeg_dir = os.path.dirname(WORKING_DIR)
    ffmepg_bin_path = os.path.join(ffmpeg_dir, "ffmpeg") if platform.system(
    ) != "Windows" else os.path.join(ffmpeg_dir, "ffmpeg") + ".exe"
    ffmpeg_installed = True if shutil.which("ffmpeg") or os.path.exists(
        ffmepg_bin_path) and os.access(ffmepg_bin_path, os.X_OK) else False

    if ffmpeg_installed:
        if os.path.exists(cache_dir):
            pass
    else:
        print("FFmpeg is required for program functionality. attempting to install")
        ffmpeg_path = asyncio.run(install_ffmpeg())
        print(ffmpeg_path)
        os.environ["ffmpeg"] = ffmpeg_path


if __name__ == "__main__":
    util.set_console_title("Convertion API | FastAPI Python")
    print(f'''
{c["CYAN"]}__        __   _                             {c["RESET"]}
{c["CYAN"]}\\ \\      / /__| | ___ ___  _ __ ___   ___   {c["RESET"]}
{c["CYAN"]} \\ \\ /\\ / / _ \\ |/ __/ _ \\| '_ ` _ \\ / _ \\  {c["RESET"]}
{c["CYAN"]}  \\ V  V /  __/ | (_| (_) | | | | | |  __/  {c["RESET"]}
{c["CYAN"]}   \\_/\\_/ \\___|_|\\___\\___/|_| |_| |_|\\___|  {c["RESET"]}

{c["CYAN"]}{c["RESET"]}{c["BOLD"]}{c["LIGHT_YELLOW"]}Video to Audio convertion API{c["RESET"]}{c["CYAN"]}{c["RESET"]}
Starting setup and environment check process...
''')

    setup()
    print(
        f"{c['LIGHT_GREEN']}Working directory and dependency checks completed{c['RESET']}, "
        f"if you encounter any {c['RED']}{c['BOLD']}{c['UNDERLINE']}BUGS{c['RESET']} "
        "please report them at:"
    )
    print(
        f"{c['UNDERLINE']}"
        f"{c['BRIGHT_WHITE']}Github.com"
        f"{c['BOLD']}{c['BRIGHT_WHITE']}/"
        f"{c['BLUE']}{c['BOLD']}yPiuro"
        f"{c['NO_BOLD']}{c['BRIGHT_WHITE']}/"
        f"{c['LIGHT_YELLOW']}convertion_api"
        f"{c['RESET']}\n\n"
    )
    uvicorn.run(server.app, host="0.0.0.0", port=8000)
