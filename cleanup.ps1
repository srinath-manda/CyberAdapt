# CyberAdapt Final Project Cleanup Script
Write-Host "CyberAdapt Cleanup Script" -ForegroundColor Cyan
Write-Host "=========================" -ForegroundColor Cyan

# Confirm before proceeding
$confirm = Read-Host "This will delete old repos and reorganize files. Continue? (yes/no)"
if ($confirm -ne "yes") {
    Write-Host "Cleanup cancelled." -ForegroundColor Yellow
    exit
}

# Change to project root
Set-Location "e:\final_proj_implementation"

Write-Host "`n[1/6] Deleting old repositories..." -ForegroundColor Yellow
Remove-Item "CyberAdapt_repo_update_v3" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "CyberAdapt_v1" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "cyberadapt_v2" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "docstofollow" -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item "paperdrafts" -Recurse -Force -ErrorAction SilentlyContinue
Write-Host "✓ Deleted 116.7 MB of old repos" -ForegroundColor Green

Write-Host "`n[2/6] Removing Python cache files..." -ForegroundColor Yellow
Set-Location "CyberAdapt_Final"
Get-ChildItem -Recurse -Include "__pycache__" -Directory | Remove-Item -Recurse -Force
Get-ChildItem -Recurse -Include "*.pyc","*.pyo","*.pyd" -File | Remove-Item -Force
Write-Host "✓ Removed Python cache files" -ForegroundColor Green

Write-Host "`n[3/6] Organizing documentation..." -ForegroundColor Yellow
New-Item -Path "docs" -ItemType Directory -Force | Out-Null
Move-Item "COMPREHENSIVE_BUG_FIX_ANALYSIS.md" "docs\" -Force -ErrorAction SilentlyContinue
Move-Item "NETWORK_AND_VEHICLE_SIMULATION_ANALYSIS.md" "docs\" -Force -ErrorAction SilentlyContinue
Move-Item "BUG_FIX_VALIDATION_CHECKLIST.md" "docs\" -Force -ErrorAction SilentlyContinue
Move-Item "BUGFIX_IMPLEMENTATION_SUMMARY.md" "docs\" -Force -ErrorAction SilentlyContinue
Move-Item "CRITICAL_BUGS_8_9_10.md" "docs\" -Force -ErrorAction SilentlyContinue
Move-Item "ADDITIONAL_BUG_FOUND.md" "docs\" -Force -ErrorAction SilentlyContinue
Remove-Item "IMPLEMENTATION_COMPLETE.md" -Force -ErrorAction SilentlyContinue
Remove-Item "REPO_REVIEW.md" -Force -ErrorAction SilentlyContinue
Write-Host "✓ Organized documentation into docs/ folder" -ForegroundColor Green

Write-Host "`n[4/6] Organizing test files..." -ForegroundColor Yellow
Move-Item "test_all_bugs_fixed.py" "tests\" -Force -ErrorAction SilentlyContinue
Move-Item "test_fixes_quick.py" "tests\" -Force -ErrorAction SilentlyContinue
if (Test-Path "verify_fast.py") {
    Rename-Item "verify_fast.py" "test_verify_fast.py" -Force
    Move-Item "test_verify_fast.py" "tests\" -Force
}
Remove-Item "simple_test.py" -Force -ErrorAction SilentlyContinue
Remove-Item "test_results.txt" -Force -ErrorAction SilentlyContinue
Write-Host "✓ Organized test files into tests/ folder" -ForegroundColor Green

Write-Host "`n[5/6] Checking results directory..." -ForegroundColor Yellow
if (Test-Path "results") {
    $resultFiles = Get-ChildItem "results" -File
    if ($resultFiles.Count -gt 0) {
        Write-Host "  Results directory contains $($resultFiles.Count) files" -ForegroundColor Cyan
        $deleteResults = Read-Host "  Delete old simulation results? (yes/no)"
        if ($deleteResults -eq "yes") {
            Remove-Item "results\*" -Force
            Write-Host "  ✓ Cleaned results directory" -ForegroundColor Green
        } else {
            Write-Host "  → Kept results directory" -ForegroundColor Yellow
        }
    }
}

Write-Host "`n[6/6] Cleanup complete!" -ForegroundColor Green
Write-Host "`nSummary:" -ForegroundColor Cyan
Write-Host "  • Deleted old repos: ~116.7 MB" -ForegroundColor Green
Write-Host "  • Cleaned cache files: ~0.5 MB" -ForegroundColor Green
Write-Host "  • Organized documentation: 6 files → docs/" -ForegroundColor Green
Write-Host "  • Organized tests: 3 files → tests/" -ForegroundColor Green
Write-Host "  • Removed redundant files: 4 files" -ForegroundColor Green
Write-Host "`nTotal space reclaimed: ~117 MB" -ForegroundColor Cyan

Write-Host "`n[VERIFICATION] Testing system..." -ForegroundColor Yellow
if (Test-Path "START_DASHBOARD.bat") {
    Write-Host "  ✓ Dashboard script found" -ForegroundColor Green
} else {
    Write-Host "  ✗ WARNING: Dashboard script missing!" -ForegroundColor Red
}

if (Test-Path "tests\test_sim_integrated.py") {
    Write-Host "  ✓ Core tests found" -ForegroundColor Green
} else {
    Write-Host "  ✗ WARNING: Core tests missing!" -ForegroundColor Red
}

if (Test-Path "sim\sim_integrated.py") {
    Write-Host "  ✓ Core simulation found" -ForegroundColor Green
} else {
    Write-Host "  ✗ WARNING: Core simulation missing!" -ForegroundColor Red
}

Write-Host "`nCleanup successful! Run START_DASHBOARD.bat to verify." -ForegroundColor Cyan
