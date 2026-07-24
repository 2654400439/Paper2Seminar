param(
    [Parameter(Mandatory=$true)]
    [string]$InputPptx,

    [Parameter(Mandatory=$true)]
    [string]$OutputDir,

    [int]$Dpi = 120
)

$ErrorActionPreference = "Stop"
$inputPath = (Resolve-Path -LiteralPath $InputPptx).Path
$outputPath = $ExecutionContext.SessionState.Path.GetUnresolvedProviderPathFromPSPath($OutputDir)
New-Item -ItemType Directory -Force -Path $outputPath | Out-Null
$pdfPath = Join-Path $outputPath "deck.pdf"

$powerPoint = New-Object -ComObject PowerPoint.Application
try {
    $presentation = $powerPoint.Presentations.Open($inputPath, $true, $false, $false)
    try {
        $presentation.SaveAs($pdfPath, 32)
    }
    finally {
        $presentation.Close()
        [System.Runtime.InteropServices.Marshal]::ReleaseComObject($presentation) | Out-Null
    }
}
finally {
    $powerPoint.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($powerPoint) | Out-Null
}

$prefix = Join-Path $outputPath "slide"
& pdftoppm -png -r $Dpi $pdfPath $prefix
if ($LASTEXITCODE -ne 0) { throw "pdftoppm failed with exit code $LASTEXITCODE" }

$count = (Get-ChildItem -LiteralPath $outputPath -Filter "slide-*.png" -File).Count
if ($count -eq 0) { throw "No slide PNGs were generated." }
Write-Output "Rendered $count slides to $outputPath"
