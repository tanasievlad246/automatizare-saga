$ErrorActionPreference = 'Stop'
try {
    Add-Type -AssemblyName System.Security
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $now = Get-Date
    $mine = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2Collection
    Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt $now } | ForEach-Object { [void]$mine.Add($_) }
    $picked = [System.Security.Cryptography.X509Certificates.X509Certificate2UI]::SelectFromCollection(
        $mine, 'AutoSaga', 'Alegeti certificatul cu care intrati in SPV.',
        [System.Security.Cryptography.X509Certificates.X509SelectionFlag]::SingleSelection)
    if ($picked.Count -eq 0) { '{"cancelled": true}'; exit 0 }
    $answer = Invoke-WebRequest -Uri $env:AUTOSAGA_AUTHORIZE_URL -Certificate $picked[0] -MaximumRedirection 0 -UseBasicParsing -ErrorAction SilentlyContinue
    @{ location = [string]$answer.Headers.Location } | ConvertTo-Json -Compress
} catch {
    @{ error = $_.Exception.Message } | ConvertTo-Json -Compress
}
