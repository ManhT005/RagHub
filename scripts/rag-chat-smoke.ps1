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

    [string]$ResultPath,

    [string]$EnvFile = '.env'
)

$ErrorActionPreference = 'Stop'
$apiRoot = "$($BaseUrl.TrimEnd('/'))/api/v1"
$runId = [guid]::NewGuid().ToString('N').Substring(0, 12)
$temporaryDocument = $null

function Import-DotEnv {
    param([Parameter(Mandatory)][string]$Path)

    if (-not (Test-Path -LiteralPath $Path -PathType Leaf)) {
        return
    }
    foreach ($rawLine in Get-Content -LiteralPath $Path) {
        $line = $rawLine.Trim()
        if (-not $line -or $line.StartsWith('#')) {
            continue
        }
        if ($line.StartsWith('export ')) {
            $line = $line.Substring(7).Trim()
        }
        $separator = $line.IndexOf('=')
        if ($separator -le 0) {
            continue
        }
        $name = $line.Substring(0, $separator).Trim()
        $value = $line.Substring($separator + 1).Trim()
        if (
            $value.Length -ge 2 -and
            (($value.StartsWith('"') -and $value.EndsWith('"')) -or
            ($value.StartsWith("'") -and $value.EndsWith("'")))
        ) {
            $value = $value.Substring(1, $value.Length - 2)
        }
        $existing = [Environment]::GetEnvironmentVariable($name, 'Process')
        if ([string]::IsNullOrWhiteSpace($existing)) {
            [Environment]::SetEnvironmentVariable($name, $value, 'Process')
        }
    }
}

Import-DotEnv -Path $EnvFile

function Get-RequiredEnvironmentValue {
    param([Parameter(Mandatory)][string]$Name)

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        throw "Environment variable $Name is required for External mode."
    }
    return $value
}

function Get-EnvironmentValueOrDefault {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][string]$Default
    )

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }
    return $value
}

function Get-ExternalSecret {
    param([Parameter(Mandatory)][string]$SpecificName)

    $specific = [Environment]::GetEnvironmentVariable($SpecificName)
    if (-not [string]::IsNullOrWhiteSpace($specific)) {
        return $specific
    }
    return Get-RequiredEnvironmentValue 'GEMINI_API_KEY'
}

function Get-EnvironmentBooleanOrDefault {
    param(
        [Parameter(Mandatory)][string]$Name,
        [Parameter(Mandatory)][bool]$Default
    )

    $value = [Environment]::GetEnvironmentVariable($Name)
    if ([string]::IsNullOrWhiteSpace($value)) {
        return $Default
    }
    $parsed = $false
    if (-not [bool]::TryParse($value, [ref]$parsed)) {
        throw "Environment variable $Name must be true or false."
    }
    return $parsed
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
    $request = [System.Net.Http.HttpRequestMessage]::new(
        [System.Net.Http.HttpMethod]::Post,
        "$apiRoot/chatbots/$ChatbotId/chat"
    )
    $request.Content = $content
    $response = $null
    $reader = $null
    $stream = $null
    $events = [System.Collections.Generic.List[object]]::new()
    $eventName = $null
    $firstTokenMs = $null
    $doneMs = $null
    $stopwatch = [System.Diagnostics.Stopwatch]::StartNew()
    try {
        $response = $client.SendAsync(
            $request,
            [System.Net.Http.HttpCompletionOption]::ResponseHeadersRead
        ).GetAwaiter().GetResult()
        if (-not $response.IsSuccessStatusCode) {
            $body = $response.Content.ReadAsStringAsync().GetAwaiter().GetResult()
            throw "Chat failed with HTTP $([int]$response.StatusCode): $body"
        }
        $stream = $response.Content.ReadAsStreamAsync().GetAwaiter().GetResult()
        $reader = [System.IO.StreamReader]::new($stream)
        while (-not $reader.EndOfStream) {
            $line = $reader.ReadLineAsync().GetAwaiter().GetResult()
            if ($line.StartsWith('event: ')) {
                $eventName = $line.Substring(7).Trim()
            }
            elseif ($line.StartsWith('data: ') -and $eventName) {
                $elapsedMs = [int64]$stopwatch.ElapsedMilliseconds
                $events.Add([pscustomobject]@{
                    name = $eventName
                    data = $line.Substring(6) | ConvertFrom-Json
                    received_at_ms = $elapsedMs
                })
                if ($eventName -eq 'token' -and $null -eq $firstTokenMs) {
                    $firstTokenMs = $elapsedMs
                }
                if ($eventName -eq 'done') {
                    $doneMs = $elapsedMs
                }
                $eventName = $null
            }
        }
    }
    finally {
        $stopwatch.Stop()
        if ($reader) { $reader.Dispose() }
        if ($stream) { $stream.Dispose() }
        if ($response) { $response.Dispose() }
        $request.Dispose()
        $content.Dispose()
        $client.Dispose()
    }
    return [pscustomobject]@{
        events = $events.ToArray()
        client_first_token_ms = $firstTokenMs
        client_total_latency_ms = if ($null -ne $doneMs) { $doneMs } else { $stopwatch.ElapsedMilliseconds }
        token_event_count = @($events | Where-Object { $_.name -eq 'token' }).Count
    }
}

if ($Mode -eq 'External') {
    $embeddingConfiguration = @{
        name = "External embedding $runId"
        provider_type = Get-EnvironmentValueOrDefault `
            'RAGHUB_EXTERNAL_EMBEDDING_PROVIDER_TYPE' 'GOOGLE_GEMINI'
        capability = 'EMBEDDING'
        base_url = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_EMBEDDING_BASE_URL'
        model = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_EMBEDDING_MODEL'
        dimension = [int](Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_EMBEDDING_DIMENSION')
        secret = Get-ExternalSecret 'RAGHUB_EXTERNAL_EMBEDDING_API_KEY'
        config_json = @{}
    }
    $chatConfiguration = @{
        name = "External chat $runId"
        provider_type = Get-EnvironmentValueOrDefault `
            'RAGHUB_EXTERNAL_CHAT_PROVIDER_TYPE' 'GOOGLE_GEMINI'
        capability = 'CHAT'
        base_url = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_CHAT_BASE_URL'
        model = Get-RequiredEnvironmentValue 'RAGHUB_EXTERNAL_CHAT_MODEL'
        secret = Get-ExternalSecret 'RAGHUB_EXTERNAL_CHAT_API_KEY'
        config_json = @{
            include_stream_usage = Get-EnvironmentBooleanOrDefault `
                'RAGHUB_EXTERNAL_INCLUDE_STREAM_USAGE' $false
        }
    }
}
else {
    $embeddingConfiguration = @{
        name = "Local embedding $runId"
        provider_type = 'LOCAL_SENTENCE_TRANSFORMER'
        capability = 'EMBEDDING'
        base_url = $null
        model = Get-EnvironmentValueOrDefault `
            'RAGHUB_LOCAL_EMBEDDING_MODEL' `
            'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2'
        dimension = [int](Get-EnvironmentValueOrDefault `
            'RAGHUB_LOCAL_EMBEDDING_DIMENSION' '384')
        config_json = @{}
    }
    $chatConfiguration = @{
        name = "Local chat $runId"
        provider_type = 'OLLAMA'
        capability = 'CHAT'
        base_url = Get-EnvironmentValueOrDefault `
            'RAGHUB_OLLAMA_BASE_URL' 'http://ollama:11434'
        model = Get-EnvironmentValueOrDefault 'OLLAMA_MODEL' 'gemma3:1b'
        config_json = @{ read_timeout = 180.0 }
    }
}

try {
    Invoke-RestMethod -Method Get -Uri "$($BaseUrl.TrimEnd('/'))/health/ready" | Out-Null

    $email = "rag-smoke-$runId@example.com"
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
        -Configuration $embeddingConfiguration
    $chatProvider = New-Provider -Headers $headers `
        -OrganizationId $organization.id `
        -Configuration $chatConfiguration

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
    $streamResult = Read-ChatEvents `
        -ChatbotId $chatbot.id `
        -Message $Question `
        -Headers $headers
    $events = @($streamResult.events)
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
    $firstTokenEvent = $events | Where-Object { $_.name -eq 'token' } | Select-Object -First 1
    if ($null -eq $streamResult.client_first_token_ms) {
        throw 'The client did not observe a token event in the live response stream.'
    }
    if ($firstTokenEvent.received_at_ms -ge $doneEvent.received_at_ms) {
        throw 'The first token was not received before the done event; proxy buffering is suspected.'
    }
    if (
        $doneEvent.data.first_token_ms -and
        $streamResult.client_first_token_ms -lt $doneEvent.data.first_token_ms
    ) {
        throw 'Client TTFT cannot be lower than provider-side TTFT.'
    }
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
        provider_first_token_ms = $doneEvent.data.first_token_ms
        provider_total_latency_ms = $doneEvent.data.latency_ms
        client_first_token_ms = $streamResult.client_first_token_ms
        client_total_latency_ms = $streamResult.client_total_latency_ms
        token_event_count = $streamResult.token_event_count
        incremental_stream_verified = $true
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
