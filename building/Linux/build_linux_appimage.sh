#!/bin/bash

cd ..
rm -rf build dist
pyinstaller anaouder.spec

cd building
rm -rf Anaouder.AppDir
mkdir Anaouder.AppDir
mv ../dist/Anaouder/* Anaouder.AppDir/
cp ../icons/anaouder_256.png  Anaouder.AppDir/anaouder.png
cp Anaouder.desktop Anaouder.AppDir/
ln -s Anaouder Anaouder.AppDir/AppRun

rm -f Anaouder*.AppImage
./appimagetool-x86_64.AppImage Anaouder.AppDir
