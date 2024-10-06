#!/bin/bash

# Check if the script is run as root or using sudo
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or use sudo"
    exit
fi

# Install the desktop menu entry

xdg-desktop-menu install anaouder-editor.desktop

# Install the mime file type
xdg-mime install anaouder-ali_filetype.xml

# Link mime file types to the application
xdg-mime default anaouder-editor.desktop text/x-ali
xdg-mime default anaouder-editor.desktop application/x-subrip
