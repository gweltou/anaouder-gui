#!/bin/bash

# Install the desktop menu entry
xdg-desktop-menu install anaouder.desktop

# Install the mime file type
xdg-mime install anaouder-ali_filetype.xml

# Link mime file types to the application
xdg-mime default anaouder.desktop text/x-ali
xdg-mime default anaouder.desktop application/x-subrip
