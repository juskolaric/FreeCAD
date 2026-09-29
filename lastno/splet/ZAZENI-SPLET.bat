@echo off
setlocal
rem ZAZENI-SPLET.bat: zazene lastno gradnjo FreeCAD-a s spletnim streznikom (okno FreeCAD-a se takoj skrije)
rem in odpre brskalnik na http://127.0.0.1:3020/. Program mora biti ze preveden in namescen (ZAZENI.bat).
rem Ce streznik ze tece, samo odpre brskalnik. Okno FreeCAD-a pokaze gumb v brskalniku ali SPLET_OKNO=vidno.
cd /d "%~dp0..\.."
set "PIXI=%LOCALAPPDATA%\pixi\bin\pixi.exe"
if not exist "%PIXI%" set "PIXI=pixi"
curl -s -m 2 -o nul http://127.0.0.1:3020/stanje
if not errorlevel 1 (
  echo Spletni streznik ze tece - odpiram brskalnik.
  start "" http://127.0.0.1:3020/
  exit /b 0
)
set "SKRIPTA=%~dp0streznik.py"
set "SKRIPTA=%SKRIPTA:\=/%"
if "%SPLET_OKNO%"=="" set "SPLET_OKNO=skrito"
echo Zaganjam FreeCAD (okno %SPLET_OKNO%) s spletnim streznikom na http://127.0.0.1:3020/ ...
start "FreeCAD splet" /min "%PIXI%" run -- .pixi/envs/default/Library/bin/FreeCAD.exe "%SKRIPTA%"
endlocal
