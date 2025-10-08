#! /usr/bin/env python3

import sys
import logging
import cProfile
import pstats
from pstats import SortKey

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
        try:
            import pyi_splash
            pyi_splash.close()
        except ImportError:
            pass

    ret = main(argv)
    
    if profiling:
        profiler.disable()

        stats = pstats.Stats(profiler)
        stats.sort_stats(SortKey.CUMULATIVE)
        stats.print_stats(50)
    
    sys.exit(ret)