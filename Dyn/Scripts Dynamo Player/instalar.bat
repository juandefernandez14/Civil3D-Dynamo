@echo off
setlocal enabledelayedexpansion
rem ================================================================
rem  Instalador Pipeline v2 - copia pipeline.py donde el Python de
rem  Dynamo lo encuentra. Dynamo (Civil 3D 2024) usa un Python 3.9
rem  EMBEBIDO en %LOCALAPPDATA%\python-3.9.x-embed-amd64, que NO lee
rem  el site-packages de usuario: hay que copiar dentro de esa
rem  carpeta. Si ademas existe el site-packages clasico, se copia
rem  tambien (no molesta y cubre otras instalaciones).
rem  Doble clic, una vez por usuario y maquina. Con Civil 3D CERRADO.
rem ================================================================

echo.
echo  Instalador Pipeline v2
echo  ----------------------
echo  Origen : %~dp0pipeline.py
echo.

if not exist "%~dp0pipeline.py" (
    echo  [KO] No encuentro pipeline.py junto a este .bat.
    echo       Copia los dos ficheros a la misma carpeta y repite.
    echo.
    pause
    exit /b 1
)

set NOK=0

rem --- 1) Python embebido de Dynamo (el que usa Civil 3D 2024) -------
set EMB=
for /d %%D in ("%LOCALAPPDATA%\python-3.9*-embed-amd64") do set EMB=%%~fD
if defined EMB (
    copy /Y "%~dp0pipeline.py" "!EMB!\" >nul
    if exist "!EMB!\pipeline.py" (
        echo  [OK] Python embebido de Dynamo:
        echo       !EMB!\pipeline.py
        set /a NOK+=1
    ) else (
        echo  [KO] No pude copiar en !EMB!
    )
) else (
    echo  [--] No hay Python embebido en %LOCALAPPDATA% ^(python-3.9*-embed-amd64^).
    echo       Si Dynamo aun no se ha abierto nunca en esta maquina, abre
    echo       Dynamo una vez, cierra Civil 3D y repite este instalador.
)

rem --- 2) site-packages de usuario (otras instalaciones / openpyxl) ---
set SP=%APPDATA%\Python\Python39\site-packages
if not exist "%SP%" mkdir "%SP%" >nul 2>&1
copy /Y "%~dp0pipeline.py" "%SP%\" >nul
if exist "%SP%\pipeline.py" (
    echo  [OK] site-packages de usuario:
    echo       %SP%\pipeline.py
    set /a NOK+=1
)

rem --- 3) limpiar restos del modulo antiguo -------------------------
if defined EMB if exist "!EMB!\lynka_pipeline.py" del /q "!EMB!\lynka_pipeline.py"
if exist "%SP%\lynka_pipeline.py" del /q "%SP%\lynka_pipeline.py"

echo.
if %NOK% GEQ 1 (
    echo  Instalado en %NOK% ubicacion^(es^). Abre Civil 3D y ejecuta una
    echo  fase: la primera linea del CONFIG_LOG debe decir
    echo  "pipeline.py: importado desde ...".
    echo.
    echo  Recuerda: modulo nuevo = doble clic otra vez. Tras actualizar
    echo  Civil 3D o Dynamo, repetir ^(la carpeta embebida puede cambiar^).
) else (
    echo  [KO] No se pudo instalar en ninguna ubicacion. Revisa permisos.
)
echo.
pause
