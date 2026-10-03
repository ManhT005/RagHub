param(
    [string]$EnvFile = ".env",
    [string]$ComposeFile = "infrastructure/docker-compose.yml",
    [string]$OrganizationSlug = "raghub-test",
    [string]$OrganizationName = "RagHub Test",
    [string]$Admin1Email = "admin1@example.com",
    [string]$Admin1Password = "RagHubTest123!",
    [string]$Admin2Email = "admin2@example.com",
    [string]$Admin2Password = "RagHubTest123!"
)

$ErrorActionPreference = "Stop"

function Invoke-Compose {
    param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Args)

    & docker compose --env-file $EnvFile -f $ComposeFile @Args
    if ($LASTEXITCODE -ne 0) {
        throw "docker compose failed with exit code $LASTEXITCODE"
    }
}

if (-not (Test-Path $EnvFile)) {
    if (Test-Path ".env.example") {
        Copy-Item ".env.example" $EnvFile
        Write-Host "Created $EnvFile from .env.example"
    }
    else {
        throw "Cannot find $EnvFile or .env.example"
    }
}

Write-Host ""
Write-Host "==> Starting RagHub" -ForegroundColor Cyan
Invoke-Compose up -d --wait

Write-Host ""
Write-Host "==> Seeding test accounts" -ForegroundColor Cyan

$Payload = @{
    organization_slug = $OrganizationSlug
    organization_name = $OrganizationName
    accounts = @(
        @{
            email = $Admin1Email
            password = $Admin1Password
        },
        @{
            email = $Admin2Email
            password = $Admin2Password
        }
    )
} | ConvertTo-Json -Depth 5 -Compress

$Payload | & docker compose --env-file $EnvFile -f $ComposeFile `
    exec -T api python -m app.seed_test_admins

if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Seed failed." -ForegroundColor Red
    Write-Host "Check API/database migration and whether the selected accounts already exist with incompatible permissions." -ForegroundColor Yellow
    exit $LASTEXITCODE
}

Write-Host ""
Write-Host "==> Verifying accounts" -ForegroundColor Cyan

$Sql = @"
SELECT
    u.email,
    u.status,
    m.role,
    o.slug AS organization_slug
FROM users u
JOIN memberships m
  ON m.user_id = u.id
JOIN organizations o
  ON o.id = m.organization_id
WHERE lower(u.email) IN (
    lower('$Admin1Email'),
    lower('$Admin2Email')
)
ORDER BY u.email;
"@

& docker compose --env-file $EnvFile -f $ComposeFile `
    exec -T postgres `
    psql -U raghub -d raghub `
    -c $Sql

Write-Host ""
Write-Host "Test accounts ready:" -ForegroundColor Green
Write-Host ""
Write-Host "ADMIN 1"
Write-Host "Email    : $Admin1Email"
Write-Host "Password : $Admin1Password"
Write-Host ""
Write-Host "ADMIN 2"
Write-Host "Email    : $Admin2Email"
Write-Host "Password : $Admin2Password"
Write-Host ""
Write-Host "Organization: $OrganizationName ($OrganizationSlug)"
Write-Host "Open: http://localhost:8080"