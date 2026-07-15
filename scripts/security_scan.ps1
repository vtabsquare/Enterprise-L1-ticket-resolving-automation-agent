<#
.SYNOPSIS
Runs Software Composition Analysis (SCA) on the backend dependencies.

.DESCRIPTION
This script uses pip-audit to scan the backend/requirements.txt file for known
vulnerabilities (CVEs). It is part of the automated security testing suite.
#>

$ErrorActionPreference = "Stop"

Write-Host "Starting Security Composition Analysis (SCA)..." -ForegroundColor Cyan

# Ensure pip-audit is installed
if (!(Get-Command pip-audit -ErrorAction SilentlyContinue)) {
    Write-Host "pip-audit not found. Installing..." -ForegroundColor Yellow
    python -m pip install pip-audit
}

Write-Host "Running pip-audit on backend/requirements.txt..." -ForegroundColor Cyan

$reqPath = Join-Path $PSScriptRoot "..\backend\requirements.txt"

# Run pip-audit
pip-audit -r $reqPath

if ($LASTEXITCODE -eq 0) {
    Write-Host "SCA Scan Passed! No known vulnerabilities found." -ForegroundColor Green
} else {
    Write-Host "SCA Scan Failed! Vulnerabilities detected in dependencies. Please update them." -ForegroundColor Red
    exit 1
}
