#! /usr/bin/env python3

import logging

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

    main(argv)