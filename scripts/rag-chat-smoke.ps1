[CmdletBinding()]
param(
    [ValidateSet('External', 'Local')]
    [string]$Mode = 'External',

    [string]$BaseUrl = 'http://localhost:8080',

    [ValidateScript({ -not $_ -or (Test-Path -LiteralPath $_ -PathType Leaf) })]
    [string]$DocumentPath,

    [string]$Question = 'What is the RagHub smoke test launch code?',

    [ValidateRange(10, 900)]
    [int]$PollTimeoutSeconds = 180,

    [string]$ResultPath
)

$ErrorActionPreference = 'Stop'
$apiRoot = "$($BaseUrl.TrimEnd('/'))/api/v1"
$runId = [guid]::NewGuid().ToString('N').Substring(0, 12)
$temporaryDocument = $null

function Get-RequiredEnvironmentValue {
    param([Parameter(Mandatory)][string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Environment variable $Name is required for External mode."
    }
    return $value
}

function Invoke-JsonApi {
    param(
        [Parameter(Mandatory)][string]$Method,
        [Parameter(Mandatory)][string]$Path,
        [hashtable]$Headers = @{},
        [object]$Body
    )

    $arguments = @{
        Method = $Method
        Uri = "$apiRoot$Path"
        Headers = $Headers
        ContentType = 'application/json'
    }
    if ($null -ne $Body) {
        $arguments.Body = $Body | ConvertTo-Json -Depth 10
    }
    return Invoke-RestMethod @arguments
}

function New-Provider {
    param(
        [Parameter(Mandatory)][hashtable]$Headers,
        [Parameter(Mandatory)][string]$OrganizationId,
        [Parameter(Mandatory)][hashtable]$Configuration
    )

    return Invoke-JsonApi -Method Post `
        -Path "/organizations/$OrganizationId/providers" `
        -Headers $Headers `
        -Body $Configuration
}

function Send-Document {
    param(
        [Parameter(Mandatory)][string]$Path,
        [Parameter(Mandatory)][string]$WorkspaceId,
        [Parameter(Mandatory)][hashtable]$Headers
    )

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    foreach ($entry in $Headers.GetEnumerator()) {
        $client.DefaultRequestHeaders.Add($entry.Key, [string]$entry.Value)
    }
    $multipart = [System.Net.Http.MultipartFormDataContent]::new()
    $stream = [System.IO.File]::OpenRead((Resolve-Path -LiteralPath $Path))
    $fileContent = [System.Net.Http.StreamContent]::new($stream)
    $extension = [System.IO.Path]::GetExtension($Path).ToLowerInvariant()
    $mediaType = if ($extension -eq '.pdf') { 'application/pdf' } else { 'text/plain' }
    $fileContent.Headers.ContentType = [System.Net.Http.Headers.MediaTypeHeaderValue]::Parse(
        $mediaType
    )
    $multipart.Add($fileContent, 'file', [System.IO.Path]::GetFileName($Path))
    try {
        $response = $client.PostAsync(
            "$apiRoot/workspaces/$WorkspaceId/documents", $multipart
        ).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "Document upload failed with HTTP $([int]$response.StatusCode): $body"
        }
        return $body | ConvertFrom-Json
    }
    finally {
        $fileContent.Dispose()
        $stream.Dispose()
        $multipart.Dispose()
        $client.Dispose()
    }
}

function Read-ChatEvents {
    param(
        [Parameter(Mandatory)][string]$ChatbotId,
        [Parameter(Mandatory)][string]$Message,
        [Parameter(Mandatory)][hashtable]$Headers
    )

    Add-Type -AssemblyName System.Net.Http
    $client = [System.Net.Http.HttpClient]::new()
    foreach ($entry in $Headers.GetEnumerator()) {
        $client.DefaultRequestHeaders.Add($entry.Key, [string]$entry.Value)
    }
    $payload = @{ message = $Message } | ConvertTo-Json
    $content = [System.Net.Http.StringContent]::new(
        $payload, [System.Text.Encoding]::UTF8, 'application/json'
    )
    try {
        $response = $client.PostAsync(
            "$apiRoot/chatbots/$ChatbotId/chat", $content
        ).GetAwaiter().GetResult()
        $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            throw "Chat failed with HTTP $([int]$response.StatusCode): $body"
        }
    }
    finally {
        $content.Dispose()
        $client.Dispose()
    }

    $events = [System.Collections.Generic.List[object]]::new()
    $eventName = $null
    foreach ($line in ($body -split "`r?`n")) {
        if ($line.StartsWith('event: ')) {
            $eventName = $line.Substring(7).Trim()
        }
        elseif ($line.StartsWith('data: ') -and $eventName) {
            $events.Add([pscustomobject]@{
                name = $eventName
                data = $line.Substring(6) | ConvertFrom-Json
            })
            $eventName = $null
        }
    }
    return $events
}

try {
    Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))/health/ready" | Out-Null
    if ($Mode -ne 'External') {
        throw 'Local mode will be enabled by the next implementation phase.'
    }

    $email = "rag-smoke-$runId@example.test"
    $password = "RagHub-$runId!"
    $auth = Invoke-JsonApi -Method Post -Path '/auth/register' -Body @{
        email = $email
        password = $password
    }
    $authHeaders = @{ Authorization = "Bearer $($auth.access_token)" }
    $organization = Invoke-JsonApi -Method Post -Path '/organizations' `
        -Headers $authHeaders `
        -Body @{ name = "RAG Smoke $runId"; slug = "rag-smoke-$runId" }
    $headers = @{
        Authorization = "Bearer $($auth.access_token)"
        'X-Organization-ID' = [string]$organization.id
    }
    $workspace = Invoke-JsonApi -Method Post -Path '/workspaces' -Headers $headers -Body @{
        name = "RAG Smoke $runId"
        slug = "rag-smoke-$runId"
    }

    $embeddingProvider = New-Provider -Headers $headers `
        -OrganizationId $organization.id `
        -Configuration @{
            name = "External embedding $runId"
            provider_type = 'OPENAI_COMPATIBLE'
            capability = 'EMBEDDING'
            base_url = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_EMBEDDING_BASE_URL'
            model = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_EMBEDDING_MODEL'
            dimension = [int](Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_EMBEDDING_DIMENSION')
            secret = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_EMBEDDING_API_KEY'
            config_json = @{}
        }
    $chatProvider = New-Provider -Headers $headers `
        -OrganizationId $organization.id `
        -Configuration @{
            name = "External chat $runId"
            provider_type = 'OPENAI_COMPATIBLE'
            capability = 'CHAT'
            base_url = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_CHAT_BASE_URL'
            model = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_CHAT_MODEL'
            secret = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_CHAT_API_KEY'
            config_json = @{}
        }

    Invoke-JsonApi -Method Post -Path "/providers/$($embeddingProvider.id)/test" `
        -Headers $headers | Out-Null
    Invoke-JsonApi -Method Post -Path "/providers/$($chatProvider.id)/test" `
        -Headers $headers | Out-Null
    Invoke-JsonApi -Method Patch -Path "/workspaces/$($workspace.id)/providers" `
        -Headers $headers `
        -Body @{
            embedding_provider_id = $embeddingProvider.id
            chat_provider_id = $chatProvider.id
        } | Out-Null

    if (-not $DocumentPath) {
        $temporaryDocument = Join-Path ([System.IO.Path]::GetTempPath()) "raghub-$runId.txt"
        Set-Content -LiteralPath $temporaryDocument -Encoding utf8 -Value (
            "RagHub smoke test launch code is ORBIT-$runId. " +
            'This fact exists only to validate retrieval and trusted citations.'
        )
        $DocumentPath = $temporaryDocument
    }
    $upload = Send-Document -Path $DocumentPath -WorkspaceId $workspace.id -Headers $headers

    $deadline = [DateTimeOffset]::UtcNow.AddSeconds($PollTimeoutSeconds)
    do {
        Start-Sleep -Seconds 2
        $documents = Invoke-JsonApi -Method Get `
            -Path "/workspaces/$($workspace.id)/documents" `
            -Headers $headers
        $document = $documents | Where-Object { $_.id -eq $upload.document_id } | Select-Object -First 1
        if ($document.status -eq 'FAILED') {
            throw "Ingestion failed: $($document.error_code) $($document.error_message)"
        }
    } until ($document.status -eq 'READY' -or [DateTimeOffset]::UtcNow -ge $deadline)
    if ($document.status -ne 'READY') {
        throw "Document did not become READY within $PollTimeoutSeconds seconds."
    }

    $chatbot = Invoke-JsonApi -Method Post `
        -Path "/workspaces/$($workspace.id)/chatbots" `
        -Headers $headers `
        -Body @{
            name = "RAG Smoke $runId"
            system_prompt = 'Answer concisely and cite the supplied context markers.'
            retrieval_limit = 5
            published = $true
        }
    $search = Invoke-JsonApi -Method Get `
        -Path "/workspaces/$($workspace.id)/search?q=$([uri]::EscapeDataString($Question))" `
        -Headers $headers
    $events = @(Read-ChatEvents -ChatbotId $chatbot.id -Message $Question -Headers $headers)
    $eventNames = @($events | ForEach-Object { $_.name })
    $errors = @($events | Where-Object { $_.name -eq 'error' })
    if ($errors.Count) {
        throw "Chat stream failed: $($errors[0].data.code) $($errors[0].data.message)"
    }
    foreach ($requiredEvent in @('conversation', 'citations', 'token', 'usage', 'done')) {
        if ($requiredEvent -notin $eventNames) {
            throw "Chat stream did not emit required event: $requiredEvent"
        }
    }
    $citationsEvent = $events | Where-Object { $_.name -eq 'citations' } | Select-Object -First 1
    $usageEvent = $events | Where-Object { $_.name -eq 'usage' } | Select-Object -First 1
    $doneEvent = $events | Where-Object { $_.name -eq 'done' } | Select-Object -First 1
    $citationChunkIds = @($citationsEvent.data.citations | ForEach-Object { [string]$_.chunk_id })
    $retrievedChunkIds = @($search.hits | ForEach-Object { [string]$_.chunk_id })
    if (-not $citationChunkIds.Count) {
        throw 'Chat stream returned no citations.'
    }
    foreach ($chunkId in $citationChunkIds) {
        if ($chunkId -notin $retrievedChunkIds) {
            throw "Citation chunk $chunkId was not present in scoped retrieval results."
        }
    }

    $result = [ordered]@{
        execution_date = [DateTimeOffset]::UtcNow.ToString('o')
        git_commit = (git rev-parse HEAD).Trim()
        mode = $Mode
        workspace_id = [string]$workspace.id
        embedding_provider = [string]$embeddingProvider.provider_type
        embedding_model = [string]$embeddingProvider.model
        chat_provider = [string]$chatProvider.provider_type
        chat_model = [string]$chatProvider.model
        document_id = [string]$upload.document_id
        question = $Question
        retrieved_chunk_ids = $retrievedChunkIds
        citation_ids = @($citationsEvent.data.citations | ForEach-Object { $_.citation_id })
        citation_chunk_ids = $citationChunkIds
        prompt_tokens = $usageEvent.data.prompt_tokens
        completion_tokens = $usageEvent.data.completion_tokens
        first_token_ms = $doneEvent.data.first_token_ms
        total_latency_ms = $doneEvent.data.latency_ms
        result = 'PASS'
    }
    $json = $result | ConvertTo-Json -Depth 10
    if ($ResultPath) {
        $parent = Split-Path -Parent $ResultPath
        if ($parent) {
            New-Item -ItemType Directory -Force -Path $parent | Out-Null
        }
        Set-Content -LiteralPath $ResultPath -Encoding utf8 -Value $json
    }
    $json
}
finally {
    if ($temporaryDocument -and (Test-Path -LiteralPath $temporaryDocument)) {
        Remove-Item -LiteralPath $temporaryDocument -Force
    }
}
