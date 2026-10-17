# gradnja.ps1: prevede lastno gradnjo FreeCAD-a (build/release) tako, da računalnik med gradnjo ostane uporaben:
#   - največ -Jeder vzporednih prevajalnikov (privzeto 12 od 20 niti; goli ninja jih zažene 22),
#   - proces z nižjo prednostjo (BelowNormal; podedujejo jo pixi, cmake, ninja in vsi cl.exe),
#   - izpis v build/build-<cilj>-<datum>.log, na koncu zadnjih 15 vrstic in izhodna koda.
# Zagon od koderkoli:  powershell -NoProfile -ExecutionPolicy Bypass -File lastno/gradnja.ps1 [-Jeder 12] [-Cilj release] [-Namesti]
# -Namesti po uspešni gradnji požene še install-release (kopija v .pixi/envs/default/Library).
# Nastalo 17. 10. 2026, ko je gradnja iz druge seje z 22 cl.exe za 53 min zasedla ves procesor.
param(
    [int]$Jeder = 12,
    [string]$Cilj = "release",
    [switch]$Namesti
)
$ErrorActionPreference = "Stop"
$koren = Split-Path -Parent $PSScriptRoot
Set-Location $koren
$pixi = Join-Path $env:LOCALAPPDATA "pixi\bin\pixi.exe"
if (-not (Test-Path $pixi)) { $pixi = "pixi" }
if (-not (Test-Path "build\$Cilj\build.ninja")) {
    Write-Error "build\$Cilj ni konfiguriran: najprej 'pixi run configure-$Cilj' (glej CLAUDE.md)."
}

# Nižja prednost za ta proces; otroci (pixi -> cmake -> ninja -> cl.exe) jo podedujejo.
[System.Diagnostics.Process]::GetCurrentProcess().PriorityClass = [System.Diagnostics.ProcessPriorityClass]::BelowNormal
$env:CMAKE_BUILD_PARALLEL_LEVEL = "$Jeder"

$datum = Get-Date -Format "yyyy-MM-dd"
$dnevnik = Join-Path $koren "build\build-$Cilj-$datum.log"
$napake = Join-Path $koren "build\build-$Cilj-$datum.napake.log"
Add-Content -Path $dnevnik -Encoding UTF8 -Value ("=== gradnja {0} {1:HH:mm:ss}: {2} jeder, prednost BelowNormal" -f $Cilj, (Get-Date), $Jeder)

$argumenti = @("run", "-q", "--no-progress", "--", "cmake", "--build", "build/$Cilj", "--parallel", "$Jeder")
$proces = Start-Process -FilePath $pixi -ArgumentList $argumenti -WorkingDirectory $koren -NoNewWindow -Wait -PassThru `
    -RedirectStandardOutput "$dnevnik.del" -RedirectStandardError $napake
Get-Content "$dnevnik.del" -Encoding UTF8 | Add-Content -Path $dnevnik -Encoding UTF8
Remove-Item "$dnevnik.del" -ErrorAction SilentlyContinue
$koda = $proces.ExitCode
Add-Content -Path $dnevnik -Encoding UTF8 -Value ("IZHOD={0} ({1:HH:mm:ss})" -f $koda, (Get-Date))

Get-Content $dnevnik -Encoding UTF8 -Tail 15
if ((Test-Path $napake) -and (Get-Item $napake).Length -gt 0) {
    Write-Host "--- napake/opozorila (zadnjih 10 vrstic $napake):"
    Get-Content $napake -Encoding UTF8 -Tail 10
}
if ($koda -ne 0) { Write-Host "Gradnja ni uspela (izhodna koda $koda). Dnevnik: $dnevnik"; exit $koda }

if ($Namesti) {
    Write-Host "--- namestitev (install-$Cilj) ..."
    $proces = Start-Process -FilePath $pixi -ArgumentList @("run", "-q", "--no-progress", "install-$Cilj") -WorkingDirectory $koren -NoNewWindow -Wait -PassThru
    if ($proces.ExitCode -ne 0) { Write-Host "Namestitev ni uspela (izhodna koda $($proces.ExitCode))."; exit $proces.ExitCode }
}
Write-Host "Gradnja uspela. Dnevnik: $dnevnik"
exit 0
