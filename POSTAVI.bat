@echo off
setlocal EnableDelayedExpansion
rem POSTAVI.bat: pripravi nov Windows racunalnik za to kopijo FreeCAD-a in jo prevede.
rem Potrebuje Windows 10/11 x64, internet in ~40 GB prostora. Zazeni z dvoklikom ali iz terminala
rem v mapi klona. Z argumentom --brez-gradnje samo preveri in namesti orodja.
rem Koraki: git, pixi, Visual Studio Build Tools 2022 s C++, podmoduli, gradnja (configure, build, install).
cd /d "%~dp0"

echo == 1/5 git ==
where git >nul 2>nul
if errorlevel 1 (
  echo git manjka - namestitev prek winget ...
  winget install --id Git.Git -e --silent --accept-source-agreements --accept-package-agreements
  set "PATH=%ProgramFiles%\Git\cmd;!PATH!"
)
git --version || (echo git ni na voljo. & pause & exit /b 1)

echo == 2/5 pixi ==
set "PIXI=%LOCALAPPDATA%\pixi\bin\pixi.exe"
if not exist "%PIXI%" (
  where pixi >nul 2>nul && set "PIXI=pixi"
)
if not exist "%PIXI%" if not "%PIXI%"=="pixi" (
  echo pixi manjka - namestitev prek winget ...
  winget install --id prefix-dev.pixi -e --silent --accept-source-agreements --accept-package-agreements
)
if not exist "%PIXI%" if not "%PIXI%"=="pixi" set "PIXI=%LOCALAPPDATA%\pixi\bin\pixi.exe"
"%PIXI%" --version || (echo pixi ni na voljo; odpri nov terminal in poskusi znova. & pause & exit /b 1)

echo == 3/5 Visual Studio Build Tools 2022 s C++ ==
set "VSWHERE=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\vswhere.exe"
set "VSSETUP=%ProgramFiles(x86)%\Microsoft Visual Studio\Installer\setup.exe"
set "IMA_CPP="
set "VSPOT="
if exist "%VSWHERE%" (
  for /f "usebackq delims=" %%i in (`"%VSWHERE%" -products * -requires Microsoft.VisualStudio.Component.VC.Tools.x86.x64 -property installationPath`) do set "IMA_CPP=%%i"
  for /f "usebackq delims=" %%i in (`"%VSWHERE%" -products * -latest -property installationPath`) do set "VSPOT=%%i"
)
if not "!IMA_CPP!"=="" (
  echo C++ prevajalnik je ze namescen: !IMA_CPP!
) else if not "!VSPOT!"=="" (
  echo Visual Studio je namescen brez C++ - dodajam delovno obremenitev C++ ^(skrbniska potrditev, ~8 GB^) ...
  "%VSSETUP%" modify --installPath "!VSPOT!" --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended --passive --norestart
) else (
  echo Namescam Build Tools 2022 z delovno obremenitvijo C++ ^(skrbniska potrditev, ~8 GB^) ...
  winget install --id Microsoft.VisualStudio.2022.BuildTools -e --accept-source-agreements --accept-package-agreements --override "--passive --wait --norestart --add Microsoft.VisualStudio.Workload.VCTools --includeRecommended"
)

echo == 4/5 podmoduli ==
git submodule update --init --recursive || (echo podmoduli niso uspeli. & pause & exit /b 1)
git config core.longpaths true

if "%~1"=="--brez-gradnje" (
  echo Orodja so pripravljena. Gradnja: POSTAVI.bat brez argumenta ali ZAZENI.bat.
  exit /b 0
)

echo == 5/5 gradnja Release ^(prvic 30-90 min, okolje pixi ~10 GB, build ~4 GB^) ==
"%PIXI%" run configure-release || (echo konfiguracija ni uspela. & pause & exit /b 1)
"%PIXI%" run build-release || (echo prevajanje ni uspelo. & pause & exit /b 1)
"%PIXI%" run install-release || (echo namestitev ni uspela. & pause & exit /b 1)
echo.
echo Koncano. Zagon: ZAZENI.bat ^(namizni FreeCAD^) ali lastno\splet\ZAZENI-SPLET.bat ^(v brskalniku^).
pause
endlocal
