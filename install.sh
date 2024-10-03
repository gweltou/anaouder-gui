#!/bin/bash

# Check if the script is run as root or using sudo
if [ "$EUID" -ne 0 ]; then
    echo "Please run as root or use sudo"
    exit
fi

# Install the desktop menu entry
xdg-desktop-menu install anaouder-editor.desktop

# Install the mime file type
sudo xdg-mime install anaouder-ali_filetype.xml

# Link the mime file type to the application
xdg-mime default anaouder-editor.desktop text/x-ali
