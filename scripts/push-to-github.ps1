# gAIOps v2.0 — GitHub 推送脚本
# 用法: 在 Windows PowerShell 中运行此脚本

$RepoPath = "E:\VScode(study)\Project\g-AIOps"
$BundleFile = "$RepoPath\gaiops-v2.0-complete.bundle"

Write-Host "=== gAIOps v2.0 GitHub 推送助手 ===" -ForegroundColor Cyan
Write-Host ""

# ── 方式 A: 通过 Bundle 恢复 + 推送 ──
if (Test-Path $BundleFile) {
    Write-Host "[1/3] 从 Bundle 恢复 Git 对象..." -ForegroundColor Yellow
    cd $RepoPath
    git fetch $BundleFile master 2>&1 | Out-Null

    Write-Host "[2/3] 合并 v2.0 变更..." -ForegroundColor Yellow
    git merge FETCH_HEAD --ff-only 2>&1 | Out-Null

    Write-Host "[3/3] 推送到 GitHub..." -ForegroundColor Green
    Write-Host ""
    Write-Host "请选择推送方式:" -ForegroundColor Cyan
    Write-Host "  1) HTTPS + Personal Access Token"
    Write-Host "  2) SSH Key"
    Write-Host "  3) GitHub CLI (gh)"
    $choice = Read-Host "输入选项 (1/2/3)"

    switch ($choice) {
        "1" {
            $token = Read-Host "输入 GitHub Personal Access Token" -AsSecureString
            $tokenStr = [System.Runtime.InteropServices.Marshal]::PtrToStringAuto(
                [System.Runtime.InteropServices.Marshal]::SecureStringToBSTR($token)
            )
            git remote set-url origin "https://$tokenStr@github.com/Ryan-0625/g-AIOps.git"
            git push origin master
        }
        "2" {
            git remote set-url origin git@github.com:Ryan-0625/g-AIOps.git
            git push origin master
        }
        "3" {
            gh auth login
            gh repo sync Ryan-0625/g-AIOps --force
        }
    }
} else {
    Write-Warning "Bundle 文件不存在，使用直接推送方式..."
    git remote -v
    git push origin master
}

Write-Host ""
Write-Host "推送完成！" -ForegroundColor Green
Pause
