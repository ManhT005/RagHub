[CmdletBinding()]
param()

$ErrorActionPreference = 'Stop'
$composeFile = Join-Path $PSScriptRoot '..\infrastructure\docker-compose.yml'
$organizationId = '00000000-0000-0000-0000-000000000001'
$workspaceId = '00000000-0000-0000-0000-000000000002'

$sql = @"
INSERT INTO organizations (id, name, slug, status)
VALUES ('$organizationId', 'RagHub Demo', 'raghub-demo', 'ACTIVE')
ON CONFLICT (id) DO NOTHING;

INSERT INTO workspaces (id, organization_id, name, slug)
VALUES ('$workspaceId', '$organizationId', 'Phase One', 'phase-one')
ON CONFLICT (organization_id, slug) DO NOTHING;
"@

$sql | docker compose -f $composeFile exec -T postgres `
    psql -v ON_ERROR_STOP=1 -U raghub -d raghub

Write-Host "Organization: $organizationId"
Write-Host "Workspace:    $workspaceId"
