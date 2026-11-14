# Asks ANAF for a login with a certificate Windows holds, and prints one line of JSON:
#   {"location": "...", "tries": 1, "opened": true}   the address ANAF sent the login to in the end
#   {"cancelled": true}                               no certificate was chosen
#   {"error": "...", "tries": 1, "opened": true}      it did not go through; the text is what Windows or ANAF said
# "tries" is how many times ANAF was asked; "opened" says whether using the key first worked.
# The address to ask is read from AUTOSAGA_AUTHORIZE_URL. ANAF answers in several hops on
# its own host: each is followed with the same cookies and the same certificate. The
# address it ends on is printed, never asked, and the certificate goes to no other host.
$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
$tries = 0
$opened = $false
try {
    $first = $env:AUTOSAGA_AUTHORIZE_URL
    if (-not $first) { throw 'AUTOSAGA_AUTHORIZE_URL is not set.' }
    $anaf = ([Uri]$first).Host
    Add-Type -AssemblyName System.Security
    [Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
    $now = Get-Date
    $mine = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2Collection
    Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.HasPrivateKey -and $_.NotAfter -gt $now } | ForEach-Object { [void]$mine.Add($_) }
    $picked = [System.Security.Cryptography.X509Certificates.X509Certificate2UI]::SelectFromCollection(
        $mine, 'AutoSaga', ('Alege' + [char]0x021B + 'i certificatul cu care intra' + [char]0x021B + 'i ' + [char]0x00EE + 'n SPV.'),
        [System.Security.Cryptography.X509Certificates.X509SelectionFlag]::SingleSelection)
    if ($picked.Count -eq 0) { '{"cancelled": true}'; exit 0 }
    $certificate = $picked[0]

    # The token asks for its PIN the first time its key is used, and ANAF does not wait for
    # that: a login during which the PIN was typed came back refused, and the next one, with
    # the token already open, went through. So the key is used once here, before ANAF is
    # asked. If this cannot be done, the second try below covers it.
    try {
        $key = [System.Security.Cryptography.X509Certificates.RSACertificateExtensions]::GetRSAPrivateKey($certificate)
        if ($key) {
            [void]$key.SignData([byte[]](1..32), [System.Security.Cryptography.HashAlgorithmName]::SHA256, [System.Security.Cryptography.RSASignaturePadding]::Pkcs1)
            $opened = $true
        }
    } catch { }

    $location = $null
    while ($tries -lt 2) {
        if ($tries -gt 0) { Start-Sleep -Milliseconds 1500 }
        $tries++
        $location = $null
        $url = $first
        $session = New-Object Microsoft.PowerShell.Commands.WebRequestSession
        for ($hop = 0; $hop -lt 12 -and -not $location; $hop++) {
            $answer = $null
            $answer = Invoke-WebRequest -Uri $url -Certificate $certificate -WebSession $session -MaximumRedirection 0 -UseBasicParsing -ErrorAction SilentlyContinue
            if (-not $answer) { throw 'ANAF did not answer.' }
            $next = [string]$answer.Headers.Location
            if (-not $next) { throw ('ANAF stopped on a page instead of sending the login on (status ' + [int]$answer.StatusCode + ').') }
            $next = [Uri]::new([Uri]$url, $next)
            if ($next.Host -ne $anaf) { $location = $next.AbsoluteUri }
            elseif ($next.Scheme -ne 'https') { throw 'ANAF sent the login to an address that is not https.' }
            else { $url = $next.AbsoluteUri }
        }
        if (-not $location) { throw 'ANAF kept sending the login on, without an end.' }
        # Only a refusal is worth a second try; a code, or any other answer, ends it.
        if ($location -notmatch '[?&]error=access_denied') { break }
    }
    @{ location = $location; tries = $tries; opened = $opened } | ConvertTo-Json -Compress
} catch {
    $said = [string]$_.Exception.Message
    if ($_.ErrorDetails) { $said += ' | ' + $_.ErrorDetails.Message }
    @{ error = ($said -replace '\s+', ' '); tries = $tries; opened = $opened } | ConvertTo-Json -Compress
}
