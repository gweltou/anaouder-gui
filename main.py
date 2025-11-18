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
    if platform.system() == "Linux":
        # Define paths to the bundled binaries (matches your spec file structure)
        ffmpeg_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "linux", "ffmpeg")
        ffprobe_path = os.path.join(bundle_dir, "static_ffmpeg", "bin", "linux", "ffprobe")
        
        # Tell static_ffmpeg (and other libs) where to find them
        # This prevents static_ffmpeg from trying to create a lock file
        os.environ["FFMPEG_BINARY"] = ffmpeg_path
        os.environ["FFPROBE_BINARY"] = ffprobe_path
        
        # Optional: Add to system PATH just in case subprocess calls need it
        os.environ["PATH"] += os.pathsep + os.path.dirname(ffmpeg_path)


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
    
    if hasattr(sys, '_MEIPASS'):
        # We are running in a PyInstaller bundle
        try:
            import pyi_splash
            pyi_splash.close()
        except ImportError:
            pass
    else:
        import static_ffmpeg
        static_ffmpeg.add_paths()

    ret = main(argv)
    
    if profiling:
        profiler.disable()

        stats = pstats.Stats(profiler)
        stats.sort_stats(SortKey.CUMULATIVE)
        stats.print_stats(50)
    
    sys.exit(ret)