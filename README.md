# Anaouder-mich

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

## Staliañ dindan Linux

Ret e vo cheñch al linenn `exec=` er restr `anaouder-editor.desktop` da gentañ.

```bash
chmod +x install.sh
sudo ./install.sh
```
