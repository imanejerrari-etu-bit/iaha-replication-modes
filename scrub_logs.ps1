# scrub_logs.ps1 - redact secrets from logs/text files before publishing the repository.
# Run from the repository root:  powershell -ExecutionPolicy Bypass -File .\scrub_logs.ps1
Get-ChildItem -Recurse -File -Include *.txt,*.log,*.md | ForEach-Object {
    $c = Get-Content -LiteralPath $_.FullName -Raw
    if ($null -eq $c) { return }
    $n = $c -replace 'PGPASSWORD=\S+', 'PGPASSWORD=REDACTED'
    if ($n -ne $c) {
        Set-Content -LiteralPath $_.FullName -Value $n -NoNewline -Encoding UTF8
        Write-Host "scrubbed $($_.FullName)"
    }
}
Write-Host "Done. Re-check with: Select-String -Path *.txt,results\*.txt -Pattern 'PGPASSWORD=' | Select-Object -First 5"
