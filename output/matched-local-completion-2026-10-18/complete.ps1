$ErrorActionPreference = 'Stop'
Set-StrictMode -Version Latest
$projectDirectory = 'C:/Users/DELL/OneDrive/Desktop/ConseqaX'
Set-Location -LiteralPath $projectDirectory
$planPath = Join-Path $PSScriptRoot 'plan.json'
$completionPlan = Get-Content -LiteralPath $planPath -Raw | ConvertFrom-Json
function Assert-CompletionSources {
    foreach ($sourceFile in $completionPlan.files.PSObject.Properties) {
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $sourceFile.Name).Hash.ToLowerInvariant()
        if ($sourceHash -ne $sourceFile.Value) { throw 'Completion source changed; refusing automatic analysis.' }
    }
    $protocolFile = Join-Path $completionPlan.study_output 'protocol.json'
    if ((Get-FileHash -Algorithm SHA256 -LiteralPath $protocolFile).Hash.ToLowerInvariant() -ne $completionPlan.protocol_sha256) {
        throw 'Frozen protocol differs from the completion plan.'
    }
}
Assert-CompletionSources
$studyProcessInfo = Get-CimInstance Win32_Process -Filter 'ProcessId = 4264'
if ($studyProcessInfo) {
    if (-not $studyProcessInfo.CommandLine.Contains('scripts/run_matched_local_study.py run --output output/matched-local-study-2026-10-18')) {
        throw 'Study process identity changed; refusing to wait on a different task.'
    }
    Write-Output 'Waiting for the existing local study to close; no new generation is launched.'
    $waitingProcess = Get-Process -Id 4264 -ErrorAction SilentlyContinue
    if ($waitingProcess) { $waitingProcess | Wait-Process }
}
Assert-CompletionSources
Write-Output 'Study process ended. Finalization still requires a valid closed journal and no runner lock.'
& '.venv/Scripts/python.exe' 'scripts/finalize_matched_local_study.py' --study-output $completionPlan.study_output --output-dir $completionPlan.analysis_output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
$env:PYTHONPATH = 'D:/ConsequaX-Research/figure-dependencies'
$env:MPLCONFIGDIR = 'D:/ConsequaX-Research/figure-matplotlib-cache'
& '.venv/Scripts/python.exe' -c 'import matplotlib, numpy; print(matplotlib.__version__, numpy.__version__)'
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& 'C:/Users/DELL/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe' 'C:/Users/DELL/.codex/plugins/cache/openai-primary-runtime/pdf/26.1015.12040/skills/pdf/container_tools/mark_artifact_operation_started.mjs' --operation-kind create --expected-output-count 2 --output-format pdf
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& '.venv/Scripts/python.exe' 'scripts/build_matched_study_figures.py' --analysis 'output/matched-local-analysis-2026-10-18/analysis.json' --protocol 'output/matched-local-study-2026-10-18/protocol.json' --disposition 'output/matched-local-analysis-2026-10-18/final-disposition.json' --execution-diagnostics 'output/matched-local-analysis-2026-10-18/execution/execution-summary.json' --output $completionPlan.figure_output
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Output 'Analysis and figure files created. Manual results review, visual QA and paper integration remain required.'
