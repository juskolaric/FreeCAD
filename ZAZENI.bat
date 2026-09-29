@echo off
setlocal
rem ZAZENI.bat: prevede spremembe, namesti in zazene lastno gradnjo FreeCAD-a.
rem Deluje od koderkoli (dvoklik ali iz terminala), ker uporablja polno pot do pixi.
cd /d "%~dp0"
set "PIXI=%LOCALAPPDATA%\pixi\bin\pixi.exe"
if not exist "%PIXI%" set "PIXI=pixi"
if not exist "build\release\build.ninja" (
  echo [0/3] Prva konfiguracija gradnje ...
  "%PIXI%" run configure-release
  if errorlevel 1 goto napaka
)
echo [1/3] Gradnja - samo spremenjeno ...
"%PIXI%" run build-release
if errorlevel 1 goto napaka
echo [2/3] Namestitev in [3/3] zagon ...
"%PIXI%" run freecad-release
endlocal
exit /b 0
:napaka
echo.
echo Gradnja ni uspela, program ni zagnan. Preveri izpis zgoraj.
pause
exit /b 1
