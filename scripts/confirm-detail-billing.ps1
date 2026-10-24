param(
  [Parameter(Mandatory = $true)][string]$Project,
  [Parameter(Mandatory = $true)][string]$Run,
  [Parameter(Mandatory = $true)][string]$Budget,
  [Parameter(Mandatory = $true)][string]$Request,
  [Parameter(Mandatory = $true)][ValidateRange(1, 10000)][int]$Attempt,
  [Parameter(Mandatory = $true)][string]$Material,
  [switch]$Json
)
$ErrorActionPreference = 'Stop'
$billingRepositoryRoot = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
. (Join-Path $PSScriptRoot 'env.ps1')
$billingImportArguments = @('-B', (Join-Path $PSScriptRoot 'confirm-detail-billing.py'), '--project', $Project, '--run', $Run, '--budget', $Budget, '--request', $Request, '--attempt', $Attempt, '--material', $Material)
$billingOutputEncoding = $OutputEncoding
$billingConsoleEncoding = [Console]::OutputEncoding
$billingImportExit = 1
try {
  $OutputEncoding = New-Object System.Text.UTF8Encoding $false
  [Console]::OutputEncoding = $OutputEncoding
  $billingOutput = & (Join-Path $billingRepositoryRoot '.venv/Scripts/python.exe') @billingImportArguments
  $billingImportExit = $LASTEXITCODE
  if ($billingImportExit -eq 0) {
    if ($Json) { Write-Output $billingOutput }
    else {
      $billingResult = $billingOutput | ConvertFrom-Json
      Write-Output ("已保存指定请求的未扣费确认；本项目共 " + $billingResult.sharedHumanBillingSummary.confirmedNoChargeCount + " 次已确认。")
      Write-Output ("核对后占用 ¥" + $billingResult.sharedHumanBillingSummary.reconciledCommitmentCny + "；原费用记录与发送上限保持。")
    }
  }
} finally {
  $OutputEncoding = $billingOutputEncoding
  [Console]::OutputEncoding = $billingConsoleEncoding
}
exit $billingImportExit
