#!/bin/bash

# Run from the root directory

pip install .

rm -rf build dist

pyside6-lrelease translations/anaouder_fr.ts -qm translations/anaouder_fr.qm && pyside6-lrelease translations/anaouder_br.ts -qm translations/anaouder_br.qm
pyinstaller anaouder.spec

cd building/Linux
mkdir Anaouder.AppDir
mv ../../dist/Anaouder/* Anaouder.AppDir/
cp ../../icons/anaouder_256.png  Anaouder.AppDir/anaouder.png
cp Anaouder.desktop Anaouder.AppDir/
ln -s Anaouder Anaouder.AppDir/AppRun

rm -f Anaouder*.AppImage
./appimagetool-x86_64.AppImage Anaouder.AppDir
rm -rf Anaouder.AppDir
