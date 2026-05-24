$f = [System.IO.Path]::GetTempFileName()
$question = "帮我检查一下系统整体状态，包括CPU、内存、磁盘和网络连通性，然后给出一个综合报告"
Add-Content -Path $f -Value $question
Add-Content -Path $f -Value "/exit"
$cmd = "python cli/gaiops chat < `"" + $f + "`""
cmd /c $cmd
Remove-Item $f
