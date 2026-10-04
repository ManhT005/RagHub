import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { ProviderCapability, ProviderType } from '../raghub-api.service';

export interface ProviderCatalogItem {
  id: string; name: string; category: string; provider_type: ProviderType | null;
  default_base_url: string | null; capabilities: ProviderCapability[];
  supports_model_discovery: boolean; auth_type: string; docs_url: string | null;
  api_key_url: string | null; status: 'SUPPORTED' | 'COMING_SOON';
}
export interface ProviderConnection {
  id: string; organization_id: string; name: string; provider_type: ProviderType;
  base_url: string | null; enabled: boolean; has_secret: boolean;
  status: 'UNTESTED' | 'CONNECTED' | 'DEGRADED' | 'ERROR';
  last_tested_at: string | null; last_latency_ms: number | null; last_error_code: string | null;
  created_at: string; updated_at: string | null; model_count: number;
}
export interface ConnectionInput {
  name: string; provider_type: ProviderType; base_url?: string | null; secret?: string; enabled?: boolean;
}
export interface RegistryModel {
  id: string; connection_id: string | null; model: string; display_name: string | null;
  provider_name: string; provider_type: ProviderType; capability: ProviderCapability;
  dimension: number | null; availability_status: 'AVAILABLE' | 'UNAVAILABLE' | 'UNTESTED' | 'DISABLED';
  connection_status: string; connection_enabled: boolean; enabled: boolean;
  used_by_workspaces: number; last_health_check_at: string | null;
}
export interface ModelInput {
  model: string; display_name?: string; capability: ProviderCapability; dimension?: number | null;
}
export interface DiscoveredModel {
  model: string; display_name: string | null; capabilities: ProviderCapability[]; dimension: number | null;
}
export interface ConnectionTest {
  status: string; latency_ms: number; capabilities: ProviderCapability[];
  discovery_supported: boolean; error_code: string | null;
}
export function selectableModel(model: RegistryModel): boolean {
  return model.enabled && model.connection_enabled && model.connection_status === 'CONNECTED'
    && model.availability_status === 'AVAILABLE';
}
@Injectable({ providedIn: 'root' })
export class ProviderApiService {
  private readonly http = inject(HttpClient);
  private readonly base = '/api/v1';
  catalog() { return this.http.get<ProviderCatalogItem[]>(`${this.base}/ai/provider-catalog`); }
  connections(org: string) { return this.http.get<ProviderConnection[]>(`${this.base}/organizations/${org}/provider-connections`); }
  create(org: string, payload: ConnectionInput) { return this.http.post<ProviderConnection>(`${this.base}/organizations/${org}/provider-connections`, payload); }
  update(id: string, payload: Partial<Omit<ConnectionInput, 'provider_type'>>) { return this.http.patch<ProviderConnection>(`${this.base}/provider-connections/${id}`, payload); }
  remove(id: string) { return this.http.delete(`${this.base}/provider-connections/${id}`); }
  test(id: string) { return this.http.post<ConnectionTest>(`${this.base}/provider-connections/${id}/test`, {}); }
  discover(id: string) { return this.http.post<DiscoveredModel[]>(`${this.base}/provider-connections/${id}/models/discover`, {}); }
  register(id: string, payload: ModelInput) { return this.http.post<RegistryModel>(`${this.base}/provider-connections/${id}/models`, payload); }
  models(org: string) { return this.http.get<RegistryModel[]>(`${this.base}/organizations/${org}/models`); }
  workspaceModels(id: string, capability: ProviderCapability = 'EMBEDDING') { return this.http.get<RegistryModel[]>(`${this.base}/workspaces/${id}/models`, { params: { capability } }); }
  testModel(id: string) { return this.http.post<RegistryModel>(`${this.base}/models/${id}/test`, {}); }
  updateModel(id: string, enabled: boolean) { return this.http.patch<RegistryModel>(`${this.base}/models/${id}`, { enabled }); }
}
