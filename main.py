#! /usr/bin/env python3

import logging

logging.basicConfig(
    level=logging.INFO,
    format='%(levelname)s %(asctime)s %(name)s %(filename)s:%(lineno)d %(message)s',
    handlers=[
        logging.FileHandler('anaouder_app.log'),
        logging.StreamHandler()
    ]
)

import sys
from src.main import main

if __name__ == "__main__":
    main(sys.argv)