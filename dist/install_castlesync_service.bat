@echo off
setlocal enabledelayedexpansion

set SERVICE_NAME=CastleSync
set NSSM_PATH=%~dp0nssm.exe
set INSTALL_DIR=C:\Program Files\CastleSync
set EXE_NAME=castlesync.exe
set RCLONE_NAME=rclone.exe
set SETTINGS_CONF=settings.conf

REM Vérifier les droits administrateur
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Erreur: Exécutez ce script en tant qu'Administrateur!
    pause
    exit /b 1
)

REM Vérifier la présence de nssm.exe
if not exist "%NSSM_PATH%" (
    echo Erreur: nssm.exe introuvable dans %~dp0
    pause
    exit /b 1
)

REM Créer le dossier d'installation
if not exist "%INSTALL_DIR%" (
    echo 📁 Création du dossier d'installation...
    mkdir "%INSTALL_DIR%"
)

REM Copier l'exécutable CastleSync
echo 📂 Copie de %EXE_NAME%...
copy /Y "%~dp0%EXE_NAME%" "%INSTALL_DIR%\" >nul

REM Copier rclone.exe
if exist "%~dp0%RCLONE_NAME%" (
    echo 📂 Copie de %RCLONE_NAME%...
    copy /Y "%~dp0%RCLONE_NAME%" "%INSTALL_DIR%\" >nul
) else (
    echo ⚠️ Attention : %RCLONE_NAME% introuvable dans %~dp0
)

REM Copier ou créer settings.conf
if not exist "%INSTALL_DIR%\%SETTINGS_CONF%" (
    echo 📝 Création de %SETTINGS_CONF%...
    (
      echo [paths]
      echo rclone_path=%INSTALL_DIR%\rclone.exe
      echo [remote]
      echo user=
      echo host=
      echo path=
      echo password=
      echo port=22
      echo [local]
      echo default_path=
    ) > "%INSTALL_DIR%\%SETTINGS_CONF%"
) else (
    echo ✅ %SETTINGS_CONF% déjà présent.
)

REM Supprimer service existant s'il y en a un
echo 🔍 Vérification de %SERVICE_NAME%...
"%NSSM_PATH%" status %SERVICE_NAME% >nul 2>&1
if %errorlevel% equ 0 (
    echo 🔄 Service existant détecté. Arrêt et suppression...
    "%NSSM_PATH%" stop %SERVICE_NAME% confirm
    "%NSSM_PATH%" remove %SERVICE_NAME% confirm
    timeout /t 2 >nul
)

REM Installer le service
echo 🚀 Installation du service %SERVICE_NAME%...
"%NSSM_PATH%" install %SERVICE_NAME% "%INSTALL_DIR%\%EXE_NAME%"

REM Configuration NSSM
echo 🔧 Configuration du service...
"%NSSM_PATH%" set %SERVICE_NAME% DisplayName "CastleSync"
"%NSSM_PATH%" set %SERVICE_NAME% Start SERVICE_AUTO_START
"%NSSM_PATH%" set %SERVICE_NAME% AppDirectory "%INSTALL_DIR%"
"%NSSM_PATH%" set %SERVICE_NAME% AppStdout "%INSTALL_DIR%\castlesync.log"
"%NSSM_PATH%" set %SERVICE_NAME% AppStopMethodSkip 0

REM Démarrer le service
echo ▶️ Démarrage du service...
"%NSSM_PATH%" start %SERVICE_NAME%

REM Statut final
echo 🔍 Vérification du statut...
"%NSSM_PATH%" status %SERVICE_NAME%
if %errorlevel% neq 0 (
    echo ❌ Le service n'a pas démarré!
    pause
    exit /b 1
)

echo 🎉 Service %SERVICE_NAME% installé et démarré avec succès!
pause
exit /b 0
