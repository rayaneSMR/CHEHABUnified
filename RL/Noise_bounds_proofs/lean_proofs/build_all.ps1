$ErrorActionPreference = "Stop"
$leanBin = "c:\Users\Nazne\.elan\toolchains\leanprover--lean4---v4.35.0\bin\lean.exe"
$baseDir = "C:\Users\Nazne\PFE\CHEHAB\CHEHAB_noise\chehab-unified\RL\Noise_bounds_proofs\lean_proofs"
$outDir = "$baseDir\.lake\build\lib\lean"
$env:LEAN_PATH = $outDir

# Ensure directories exist
$dirs = @(
    "$outDir\BfvNoise",
    "$outDir\BfvNoise\Lemmas",
    "$outDir\BfvNoise\Expression"
)
foreach ($d in $dirs) {
    if (-not (Test-Path $d)) {
        New-Item -ItemType Directory -Path $d -Force | Out-Null
    }
}

$files = @(
    @{ src = "BfvNoise\Basic.lean"; dst = "BfvNoise\Basic.olean" },
    @{ src = "BfvNoise\Norms.lean"; dst = "BfvNoise\Norms.olean" },
    @{ src = "BfvNoise\Lemmas\KeySwitch.lean"; dst = "BfvNoise\Lemmas\KeySwitch.olean" },
    @{ src = "BfvNoise\Lemmas\Relin.lean"; dst = "BfvNoise\Lemmas\Relin.olean" },
    @{ src = "BfvNoise\Lemmas\Rotate.lean"; dst = "BfvNoise\Lemmas\Rotate.olean" },
    @{ src = "BfvNoise\Lemmas\ModSwitch.lean"; dst = "BfvNoise\Lemmas\ModSwitch.olean" },
    @{ src = "BfvNoise\Expression\Syntax.lean"; dst = "BfvNoise\Expression\Syntax.olean" },
    @{ src = "BfvNoise\Expression\Bound.lean"; dst = "BfvNoise\Expression\Bound.olean" },
    @{ src = "BfvNoise\Expression\Soundness.lean"; dst = "BfvNoise\Expression\Soundness.olean" },
    @{ src = "BfvNoise\Expression\Budget.lean"; dst = "BfvNoise\Expression\Budget.olean" },
    @{ src = "BfvNoise\CppAlignment.lean"; dst = "BfvNoise\CppAlignment.olean" },
    @{ src = "BfvNoise.lean"; dst = "BfvNoise.olean" }
)

Write-Host "Compiling Lean 4 modules in dependency order..."
foreach ($f in $files) {
    $srcPath = Join-Path $baseDir $f.src
    $dstPath = Join-Path $outDir $f.dst
    Write-Host "  Compiling $($f.src)..." -NoNewline
    & $leanBin $srcPath -o $dstPath
    if ($LASTEXITCODE -ne 0) {
        Write-Host " FAILED"
        exit 1
    }
    Write-Host " OK"
}

Write-Host "`nAll 12 Lean 4 modules compiled successfully with 0 errors!"
