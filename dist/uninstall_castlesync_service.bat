:: uninstall_castlesync_service.bat
@echo off
setlocal enabledelayedexpansion

set SERVICE_NAME=CastleSync
set NSSM_PATH=%~dp0nssm.exe
set INSTALL_DIR=C:\Program Files\CastleSync

REM Vérifier les droits administrateur
net session >nul 2>&1
if %errorlevel% neq 0 (
    echo Erreur: Exécutez ce script en tant qu'Administrateur!
    pause
    exit /b 1
)

REM Vérifier la présence de nssm.exe
if not exist "%NSSM_PATH%" (
    echo Erreur: nssm.exe introuvable dans ce dossier: %~dp0
    pause
    exit /b 1
)

REM Vérifier l'existence du service
echo 🔍 Vérification du service %SERVICE_NAME%...
"%NSSM_PATH%" status %SERVICE_NAME% >nul 2>&1
if %errorlevel% neq 0 (
    echo ⚠️ Le service %SERVICE_NAME% n'existe pas. Rien à désinstaller.
    pause
    exit /b 0
)

REM Arrêter le service
echo ⏳ Arrêt du service %SERVICE_NAME%...
"%NSSM_PATH%" stop %SERVICE_NAME%
timeout /t 2 >nul

REM Supprimer le service
echo 🗑️ Suppression du service %SERVICE_NAME%...
"%NSSM_PATH%" remove %SERVICE_NAME% confirm
timeout /t 2 >nul

REM Vérifier si le service est toujours présent
sc query %SERVICE_NAME% >nul 2>&1
if %errorlevel% equ 0 (
    echo ❌ ERREUR: La suppression du service a échoué!
    pause
    exit /b 1
)

echo ✅ Service %SERVICE_NAME% supprimé avec succès!

REM Supprimer le dossier d'installation
if exist "%INSTALL_DIR%" (
    echo 🗑️ Suppression du dossier d'installation: %INSTALL_DIR%...
    rmdir /s /q "%INSTALL_DIR%"
) else (
    echo ✅ Dossier d'installation déjà supprimé.
)

echo 🎉 Désinstallation terminée avec succès!
pause
exit /b 0
