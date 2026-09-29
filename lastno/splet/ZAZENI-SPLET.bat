@echo off
setlocal
rem ZAZENI-SPLET.bat: zazene lastno gradnjo FreeCAD-a s spletnim streznikom (dokaz koncepta)
rem in odpre brskalnik na http://127.0.0.1:3020/. Program mora biti ze prevedeni in namescen (ZAZENI.bat).
cd /d "%~dp0..\.."
set "PIXI=%LOCALAPPDATA%\pixi\bin\pixi.exe"
if not exist "%PIXI%" set "PIXI=pixi"
set "SKRIPTA=%~dp0streznik.py"
set "SKRIPTA=%SKRIPTA:\=/%"
echo Zaganjam FreeCAD s spletnim streznikom na http://127.0.0.1:3020/ ...
"%PIXI%" run -- .pixi/envs/default/Library/bin/FreeCAD.exe "%SKRIPTA%"
endlocal
