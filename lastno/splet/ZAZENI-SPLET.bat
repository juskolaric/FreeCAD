@echo off
setlocal
rem ZAZENI-SPLET.bat: zazene lastno gradnjo FreeCAD-a s spletnim streznikom in odpre brskalnik
rem na http://127.0.0.1:3020/. Program mora biti ze preveden in namescen (ZAZENI.bat).
rem Ce streznik ze tece (FreeCAD je ze odprt), samo odpre brskalnik.
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
echo Zaganjam FreeCAD s spletnim streznikom na http://127.0.0.1:3020/ ...
"%PIXI%" run -- .pixi/envs/default/Library/bin/FreeCAD.exe "%SKRIPTA%"
endlocal
