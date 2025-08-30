#! /usr/bin/env python3

import logging
import cProfile
import pstats
from pstats import SortKey

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s %(asctime)s %(name)s:%(lineno)d %(message)s',
    handlers=[
        logging.FileHandler('anaouder_app.log'),
        logging.StreamHandler()
    ]
)

import sys
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
    main(argv)
    
    if profiling:
        profiler.disable()

        stats = pstats.Stats(profiler)
        stats.sort_stats(SortKey.CUMULATIVE)
        stats.print_stats(50)