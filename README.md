# Anaouder Enterprise Edition

## Staliañ

```bash
git clone https://github.com/gweltou/anaouder-editor.git
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

## Loc'hañ

```bash
source .venv/bin/activate
python3 main.py
```

## Packaging gant PyInstaller

```bash
pyinstaller Anaouder-editor.spec
```

Lakaet e vo restr ar meziant en doser `dist`

## Enframmañ e Linux

Staliañ al "launcher" (cheñch al linenn `exec=` er restr `anaouder-editor.desktop` da gentañ) :

```bash
xdg-desktop-menu install anaouder-editor.desktop
```

Staliañ an doare restroù `ali`

```bash
sudo xdg-mime install anaouder-ali_filetype.xml
```

Liammañ ar restroù `ali` gant ar meziant :

```bash
xdg-mime default anaouder-editor.desktop text/x-ali
```