@echo off

echo Creation de l'executable CastleSync...

pyinstaller --onefile --windowed --name "castlesync" ^
  --icon "static/images/logo.ico" ^
  --add-data "static/images/banner.svg;static/images" ^
  --add-data "static/images/logo.ico;static/images" ^
  --add-data "templates;templates" ^
  --add-data "static;static" ^
  --collect-all "pystray" ^
  --collect-all "PIL" ^
  --hidden-import "pystray._win32" ^
  --hidden-import "pystray._base" ^
  app.py

echo Build termine. Verifiez le dossier 'dist'.
pause
