@echo off
setlocal
rem ZAZENI-SPLET.bat: zazene lastno gradnjo FreeCAD-a s spletnim streznikom (okno FreeCAD-a se takoj skrije)
rem in odpre brskalnik na http://127.0.0.1:3020/. Program mora biti ze preveden in namescen (ZAZENI.bat).
rem Ce streznik ze tece, samo odpre brskalnik. Okno FreeCAD-a pokaze gumb v brskalniku ali SPLET_OKNO=vidno.
rem Pixi tece brez vidne konzole (od 2026-10-07); njegov izpis gre v build\splet-zagon.log in
rem build\splet-zagon-napake.log. Program se konca z gumbom Izhod v brskalniku (ali SPLET_KONZOLA=vidna za konzolo).
cd /d "%~dp0..\.."
set "PIXI=%LOCALAPPDATA%\pixi\bin\pixi.exe"
if not exist "%PIXI%" set "PIXI=pixi"
rem Nadzorna plosca tiskalnikov (Tiskaj, vrata 3021) je v brskalniku zavihek Tiskanje: zazeni jo, ce se ne tece
rem (lasten proces brez okna in brez brskalnika; tece naprej tudi po izhodu iz FreeCAD-a). Mapa je ob repozitoriju FreeCAD.
curl -s -m 2 -o nul http://127.0.0.1:3021/api/stanje
if errorlevel 1 call :tiskaj
curl -s -m 2 -o nul http://127.0.0.1:3020/stanje
if not errorlevel 1 (
  echo Spletni streznik ze tece - odpiram brskalnik.
  start "" http://127.0.0.1:3020/
  exit /b 0
)
set "SKRIPTA=%~dp0streznik.py"
set "SKRIPTA=%SKRIPTA:\=/%"
if "%SPLET_OKNO%"=="" set "SPLET_OKNO=skrito"
if not exist build mkdir build
echo Zaganjam FreeCAD (okno %SPLET_OKNO%) s spletnim streznikom na http://127.0.0.1:3020/ ...
if "%SPLET_KONZOLA%"=="vidna" (
  start "FreeCAD splet" /min "%PIXI%" run -q --no-progress -- .pixi/envs/default/Library/bin/FreeCAD.exe "%SKRIPTA%"
) else (
  powershell -NoProfile -ExecutionPolicy Bypass -Command "Start-Process -FilePath $env:PIXI -ArgumentList @('run','-q','--no-progress','--','.pixi/envs/default/Library/bin/FreeCAD.exe',([char]34 + $env:SKRIPTA + [char]34)) -WorkingDirectory (Get-Location).Path -WindowStyle Hidden -RedirectStandardOutput 'build\splet-zagon.log' -RedirectStandardError 'build\splet-zagon-napake.log'"
)
endlocal
goto :eof

:tiskaj
rem Plosca Tiskaj: 3D print\tiskaj ob repozitoriju FreeCAD (po selitvi 3D tisk\3D print\tiskaj); sistemski Python kot Nadzorna plosca.bat.
set "TISKAJ="
if exist "..\3D print\tiskaj\streznik.py" set "TISKAJ=..\3D print\tiskaj"
if exist "..\3D tisk\3D print\tiskaj\streznik.py" set "TISKAJ=..\3D tisk\3D print\tiskaj"
if exist "..\..\3D tisk\3D print\tiskaj\streznik.py" set "TISKAJ=..\..\3D tisk\3D print\tiskaj"
if "%TISKAJ%"=="" (
  echo Plosca Tiskaj: mape 3D print\tiskaj ni - zavihek Tiskanje v brskalniku bo brez plosce.
  goto :eof
)
set "PYW=%LOCALAPPDATA%\Programs\Python\Python311\pythonw.exe"
if not exist "%PYW%" set "PYW=pythonw"
echo Zaganjam nadzorno plosco Tiskaj na http://127.0.0.1:3021/ ...
start "" /d "%TISKAJ%" "%PYW%" streznik.py --brez-brskalnika
goto :eof
