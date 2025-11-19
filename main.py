#! /usr/bin/env python3

import sys
import os
import platform
import logging
import cProfile
import pstats
from pstats import SortKey


if hasattr(sys, '_MEIPASS'):
    # We are running in a PyInstaller bundle
    bundle_dir = sys._MEIPASS
    system_name = platform.system()

    if system_name == "Linux":
        ffmpeg_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "linux", "ffmpeg")
        ffprobe_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "linux", "ffprobe")
        
    elif system_name == "Windows":
        ffmpeg_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "win32", "ffmpeg.exe")
        ffprobe_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "win32", "ffprobe.exe")
        
    elif system_name == "Darwin":
        ffmpeg_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "darwin", "ffmpeg")
        ffprobe_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "darwin", "ffprobe")

    # Apply the environment variables if we found a path
    if system_name in ("Linux", "Windows", "Darwin"):
        os.environ["FFMPEG_BINARY"] = ffmpeg_path
        os.environ["FFPROBE_BINARY"] = ffprobe_path
        os.environ["PATH"] += os.pathsep + os.path.dirname(ffmpeg_path)
else:
    # Running in normal Python environment
    import static_ffmpeg
    static_ffmpeg.add_paths()


logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s %(asctime)s %(name)s:%(lineno)d %(message)s',
    handlers=[
        # logging.FileHandler('anaouder_app.log'),
        logging.StreamHandler()
    ]
)

from src.main import main


if __name__ == "__main__":
    argv = sys.argv
    if "--debug" in argv:
        logging.getLogger().setLevel(logging.DEBUG)
        i = argv.index("--debug")
        argv.pop(i)

    profiling = False
    if "--profile" in argv:
        i = argv.index("--profile")
        argv.pop(i)
        profiling = True

    if profiling:
        profiler = cProfile.Profile()
        profiler.enable()
    
    ret = main(argv)
    
    if profiling:
        profiler.disable()

        stats = pstats.Stats(profiler)
        stats.sort_stats(SortKey.CUMULATIVE)
        stats.print_stats(50)
    
    sys.exit(ret)