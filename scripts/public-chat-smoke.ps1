param(
    [string]$BaseUrl = "http://localhost:8080/api/v1",
    [Parameter(Mandatory = $true)][string]$PublicKey,
    [string]$Origin,
    [string]$ApiKey
)

$ErrorActionPreference = "Stop"

if (-not $Origin -and -not $ApiKey) {
    throw "Provide either -Origin for browser mode or -ApiKey for server-to-server mode."
}

$headers = @{}
if ($Origin) {
    $headers["Origin"] = $Origin
}
else {
    $headers["X-RagHub-API-Key"] = $ApiKey
}

$chatbotUrl = "$BaseUrl/public/chatbots/$PublicKey"
$config = Invoke-RestMethod -Method Get -Uri "$chatbotUrl/config" -Headers $headers
$conversation = Invoke-RestMethod `
    -Method Post `
    -Uri "$chatbotUrl/conversations" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body "{}"

Write-Host "Public config OK:" $config.name
Write-Host "Conversation created:" $conversation.conversation_id
Write-Host "Starting SSE stream..."

$body = @{
    message = "Summarize the available knowledge."
    conversation_id = $conversation.conversation_id
} | ConvertTo-Json

Invoke-WebRequest `
    -Method Post `
    -Uri "$chatbotUrl/chat" `
    -Headers $headers `
    -ContentType "application/json" `
    -Body $body | Select-Object -ExpandProperty Content
