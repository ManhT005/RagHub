[CmdletBinding()]
param(
    [Parameter(Mandatory)]
    [ValidateScript({ Test-Path -LiteralPath $_ -PathType Leaf })]
    [string]$PdfPath,

    [Parameter(Mandatory)]
    [ValidateNotNullOrEmpty()]
    [string]$Query,

    [string]$BaseUrl = 'http://localhost:8080'
)

$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Net.Http
$organizationId = '00000000-0000-0000-0000-000000000001'
$workspaceId = '00000000-0000-0000-0000-000000000002'
$headers = @{ 'X-Organization-ID' = $organizationId }
$uploadUrl = "$BaseUrl/api/v1/workspaces/$workspaceId/documents"
$searchUrl = "$BaseUrl/api/v1/workspaces/$workspaceId/search?q=$([uri]::EscapeDataString($Query))"

$client = [System.Net.Http.HttpClient]::new()
$client.DefaultRequestHeaders.Add('X-Organization-ID', $organizationId)
$multipart = [System.Net.Http.MultipartFormDataContent]::new()
$stream = [System.IO.File]::OpenRead((Resolve-Path -LiteralPath $PdfPath))
$fileContent = [System.Net.Http.StreamContent]::new($stream)
$fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse(
    'application/pdf'
)
$multipart.Add($fileContent, 'file', [System.IO.Path]::GetFileName($PdfPath))

try {
    $response = $client.PostAsync($uploadUrl, $multipart).GetAwaiter().GetResult()
    $responseBody = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
    if (-not $response.IsSuccessStatusCode) {
        throw "Upload failed with HTTP $([int]$response.StatusCode): $responseBody"
    }
    $upload = $responseBody | ConvertFrom-Json
}
finally {
    $fileContent.Dispose()
    $stream.Dispose()
    $multipart.Dispose()
    $client.Dispose()
}
Write-Host "Queued document $($upload.document_id); waiting for searchable chunks..."

for ($attempt = 1; $attempt -le 60; $attempt++) {
    $result = Invoke-RestMethod -Method Get -Uri $searchUrl -Headers $headers
    if ($result.hits.Count -gt 0) {
        $result | ConvertTo-Json -Depth 6
        exit 0
    }
    Start-Sleep -Seconds 2
}

throw 'The document was not searchable within 120 seconds. Check API and worker logs.'
