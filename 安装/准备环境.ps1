param([switch]$Offline)
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
function Get-Sha256([string]$Path) {
    $Algorithm=[Security.Cryptography.SHA256]::Create()
    $Stream=[IO.File]::OpenRead($Path)
    try { return ([BitConverter]::ToString($Algorithm.ComputeHash($Stream))).Replace('-','').ToLowerInvariant() }
    finally { $Stream.Dispose(); $Algorithm.Dispose() }
}
$Repo = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
if (-not [Environment]::Is64BitOperatingSystem -or $env:PROCESSOR_ARCHITECTURE -eq 'ARM64') {
    throw '自动安装目前只验证Windows x64。'
}
if ([IO.Path]::GetPathRoot($Repo) -ne 'D:\') { throw '请把整个仓库完整解压到D盘的新目录，再运行安装入口。' }
if ((Get-PSDrive -Name D).Free -lt 1GB) { throw 'D盘至少需要1GB可用空间来准备运行时、下载与缓存。' }
$Runtime = Join-Path $Repo '运行环境'
$Cache = Join-Path $Runtime '下载与缓存'
$TempDir = Join-Path $Runtime '临时文件'
New-Item -ItemType Directory -Path $Cache,$TempDir -Force | Out-Null
$env:TEMP=$TempDir; $env:TMP=$TempDir; $env:TMPDIR=$TempDir
$env:MPLCONFIGDIR=$TempDir; $env:PIP_CACHE_DIR=$Cache
$env:PYTHONUTF8='1'; $env:PYTHONNOUSERSITE='1'; $env:PYTHONDONTWRITEBYTECODE='1'
Remove-Item Env:PYTHONPATH -ErrorAction SilentlyContinue
Remove-Item Env:PYTHONHOME -ErrorAction SilentlyContinue
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$PythonRoot = Join-Path $Runtime 'Python'
$PythonExe = Join-Path $PythonRoot 'python.exe'
$Owner = Join-Path $PythonRoot '.baihe-runtime-owner.json'
if (Test-Path -LiteralPath $PythonRoot) {
    if (-not (Test-Path -LiteralPath $Owner)) { throw '运行环境/Python已存在但不是本工具管理的环境。已保留，未覆盖。' }
    $Record=Get-Content -LiteralPath $Owner -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($Record.python -ne '3.12.10' -or $Record.arch -ne 'x64') { throw '已有独立运行时版本不符，已保留。' }
} else {
    $Archive=Join-Path $Cache 'python.3.12.10.nupkg'
    $Expected='0eb85c2dfccccf1b17352de4c397f69194035b7d37149eacc16f1147d93de3b8'
    if (-not (Test-Path -LiteralPath $Archive)) {
        if ($Offline) { throw '离线缓存缺少Python官方NuGet包，请先联网运行一次安装入口。' }
        Write-Host '下载Python软件基金会的固定版本运行时，存放在D盘……'
        $Partial=Join-Path $Cache ('python_download_'+[Guid]::NewGuid().ToString('N')+'.part')
        Invoke-WebRequest -UseBasicParsing -Uri 'https://api.nuget.org/v3-flatcontainer/python/3.12.10/python.3.12.10.nupkg' -OutFile $Partial
        if ((Get-Sha256 $Partial) -ne $Expected) { throw 'Python下载校验失败，未执行。保留临时文件供检查。' }
        Move-Item -LiteralPath $Partial -Destination $Archive
    }
    if ((Get-Sha256 $Archive) -ne $Expected) { throw 'Python缓存校验失败，未执行。' }
    Add-Type -AssemblyName System.IO.Compression.FileSystem
    $Stage=Join-Path $Runtime ('准备_python_'+[Guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $Stage | Out-Null
    $StagePrefix=[IO.Path]::GetFullPath($Stage)+[IO.Path]::DirectorySeparatorChar
    $Zip=[IO.Compression.ZipFile]::OpenRead($Archive)
    try {
        foreach ($Entry in $Zip.Entries) {
            if (-not $Entry.FullName.StartsWith('tools/')) { continue }
            $Relative=$Entry.FullName.Substring(6)
            if (-not $Relative) { continue }
            $Target=[IO.Path]::GetFullPath((Join-Path $Stage $Relative))
            if (-not $Target.StartsWith($StagePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw '运行时压缩包路径越界。' }
            if ($Entry.FullName.EndsWith('/')) { New-Item -ItemType Directory -Path $Target -Force | Out-Null; continue }
            New-Item -ItemType Directory -Path ([IO.Path]::GetDirectoryName($Target)) -Force | Out-Null
            [IO.Compression.ZipFileExtensions]::ExtractToFile($Entry,$Target,$false)
        }
    } finally { $Zip.Dispose() }
    if (-not (Test-Path -LiteralPath (Join-Path $Stage 'python.exe'))) { throw '运行时解压不完整。' }
    '{"python":"3.12.10","arch":"x64","source":"Python Software Foundation NuGet","managed_by":"baihe-sci"}' | Set-Content -LiteralPath (Join-Path $Stage '.baihe-runtime-owner.json') -Encoding UTF8
    # Verify both resolved paths before moving this project-owned runtime.
    $RuntimePrefix=[IO.Path]::GetFullPath($Runtime)+[IO.Path]::DirectorySeparatorChar
    foreach ($Candidate in @($Stage,$PythonRoot)) {
        if (-not ([IO.Path]::GetFullPath($Candidate)).StartsWith($RuntimePrefix,[StringComparison]::OrdinalIgnoreCase)) { throw '运行时目录越界，停止。' }
    }
    Move-Item -LiteralPath $Stage -Destination $PythonRoot
}
& $PythonExe -c 'import sys,struct; assert sys.version_info[:3]==(3,12,10) and struct.calcsize(chr(80))==8'
if ($LASTEXITCODE -ne 0) { throw '独立Python版本或架构不符。' }
& $PythonExe -m ensurepip --default-pip
if ($LASTEXITCODE -ne 0) { throw '独立环境的pip准备失败。' }
$Wheels=Join-Path $Cache '依赖轮子'
New-Item -ItemType Directory -Path $Wheels -Force | Out-Null
$Lock=Join-Path $PSScriptRoot 'requirements-win-py312.lock'
if (-not $Offline) {
    Write-Host '按锁定版本与SHA256下载依赖，仅使用PyPI二进制分发……'
    & $PythonExe -m pip --isolated download --require-hashes --only-binary=:all: --index-url https://pypi.org/simple --dest $Wheels --cache-dir $Cache --disable-pip-version-check -r $Lock
    if ($LASTEXITCODE -ne 0) { throw '依赖下载失败；缓存已保留，可再次运行。' }
}
& $PythonExe -m pip --isolated install --no-index --find-links $Wheels --require-hashes --only-binary=:all: --no-compile --cache-dir $Cache --disable-pip-version-check -r $Lock
if ($LASTEXITCODE -ne 0) { throw '独立依赖安装失败；未修改系统Python。' }
& $PythonExe -m pip --isolated check --disable-pip-version-check
if ($LASTEXITCODE -ne 0) { throw '独立依赖存在兼容冲突，请检查上方信息。' }
& $PythonExe (Join-Path $Repo '工作台/源码/public_setup.py')
if ($LASTEXITCODE -ne 0) { throw '环境已准备，但配套检查未通过；请保留安装检查信息。' }
Write-Host '环境与配套已配置。请读运行环境/安装检查.json；原生软件验收与文件检查分开。'
