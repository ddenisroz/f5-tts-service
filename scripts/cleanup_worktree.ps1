param(
  [switch]$Apply
)

$ErrorActionPreference = 'Stop'
$repoRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$dryPrefix = if ($Apply) { 'remove' } else { 'would remove' }
$removed = New-Object System.Collections.Generic.List[string]

function Assert-InRepo {
  param([string]$ResolvedPath)

  $rootWithSlash = $repoRoot.TrimEnd('\') + '\'
  if (
    -not $ResolvedPath.Equals($repoRoot, [System.StringComparison]::OrdinalIgnoreCase) -and
    -not $ResolvedPath.StartsWith($rootWithSlash, [System.StringComparison]::OrdinalIgnoreCase)
  ) {
    throw "Refusing to clean outside repo: $ResolvedPath"
  }
}

function Remove-ResolvedTarget {
  param([string]$ResolvedPath)

  Assert-InRepo $ResolvedPath
  $removed.Add($ResolvedPath) | Out-Null
  Write-Output "$dryPrefix $ResolvedPath"
  if ($Apply) {
    try {
      Remove-Item -LiteralPath $ResolvedPath -Recurse -Force -ErrorAction Stop
    }
    catch {
      Write-Warning "Could not remove ${ResolvedPath}: $($_.Exception.Message)"
    }
  }
}

function Remove-RepoTarget {
  param([string]$RelativePath)

  $path = Join-Path $repoRoot $RelativePath
  if (-not (Test-Path -LiteralPath $path)) {
    return
  }

  $resolved = (Resolve-Path -LiteralPath $path).Path
  Remove-ResolvedTarget $resolved
}

function Remove-NamedDirectories {
  param(
    [string[]]$Roots,
    [string[]]$Names
  )

  foreach ($rootRel in $Roots) {
    $root = Join-Path $repoRoot $rootRel
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
      continue
    }

    foreach ($name in $Names) {
      $matches = @(
        Get-ChildItem -LiteralPath $root -Recurse -Force -Directory -Filter $name -ErrorAction SilentlyContinue
      )
      foreach ($match in $matches) {
        Remove-ResolvedTarget $match.FullName
      }
    }
  }
}

function Remove-MatchedFiles {
  param(
    [string[]]$Roots,
    [string[]]$Filters
  )

  foreach ($rootRel in $Roots) {
    $root = Join-Path $repoRoot $rootRel
    if (-not (Test-Path -LiteralPath $root -PathType Container)) {
      continue
    }

    foreach ($filter in $Filters) {
      $matches = @(
        Get-ChildItem -LiteralPath $root -Recurse -Force -File -Filter $filter -ErrorAction SilentlyContinue
      )
      foreach ($match in $matches) {
        Remove-ResolvedTarget $match.FullName
      }
    }
  }
}

function Remove-GeneratedContents {
  param(
    [string]$RelativePath,
    [string[]]$KeepNames = @('.gitkeep')
  )

  $path = Join-Path $repoRoot $RelativePath
  if (-not (Test-Path -LiteralPath $path -PathType Container)) {
    return
  }

  $items = @(
    Get-ChildItem -LiteralPath $path -Force -ErrorAction SilentlyContinue |
      Where-Object { $KeepNames -notcontains $_.Name }
  )
  foreach ($item in $items) {
    Remove-ResolvedTarget $item.FullName
  }
}

$fixedTargets = @(
  '.pytest_cache',
  '.pytest_tmp',
  '_pytest_cache',
  '_pytest_tmp',
  '.ruff_cache',
  '.uv-cache',
  '.tmp',
  'tmp_runtime_logs',
  'data\pytest_tmp2',
  'data\test_tmp',
  'tests\_tmp'
)

foreach ($target in $fixedTargets) {
  Remove-RepoTarget $target
}

Remove-GeneratedContents 'data\audio'

Remove-NamedDirectories -Roots @('app', 'alembic', 'scripts', 'tests') -Names @(
  '__pycache__',
  '.pytest_cache',
  '.pytest_tmp',
  '_pytest_cache',
  '_pytest_tmp'
)

Remove-MatchedFiles -Roots @('app', 'alembic', 'scripts', 'tests', 'data') -Filters @(
  '*.pyc',
  '*.pyo',
  '*.tmp',
  '.coverage',
  '.coverage.*'
)

Remove-MatchedFiles -Roots @('data\voices') -Filters @(
  '*probe*.wav'
)

if (-not $Apply) {
  Write-Output 'Dry run only. Re-run with -Apply to delete these targets.'
}

Write-Output "targets=$($removed.Count)"
