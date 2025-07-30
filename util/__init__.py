import os
import sys

COLORS = {
    "RESET": "\033[0m",
    "BOLD": "\033[1m",
    "NO_BOLD": "\033[22m",
    "UNDERLINE": "\033[4m",
    "LIGHT_GREEN": "\033[92m",
    "BLUE": "\033[34m",
    "LIGHT_YELLOW": "\033[93m",
    "RED": "\033[31m",
    "BRIGHT_WHITE": "\033[97m",
    "CYAN": "\033[36m",     # new
}

def set_console_title(title: str):
    if sys.platform.startswith("win"):
        os.system(f"title {title}")
    else:
        print(f"\033]0;{title}\007", end="", flush=True)