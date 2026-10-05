import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { ProviderCapability, ProviderType } from '../raghub-api.service';

export interface ProviderCatalogItem {
  id: string; name: string; category: string; provider_type: ProviderType | null;
  default_base_url: string | null; capabilities: ProviderCapability[];
  supports_model_discovery: boolean; auth_type: string; docs_url: string | null;
  api_key_url: string | null; status: 'SUPPORTED' | 'BETA' | 'COMING_SOON' | 'RETIRED';
  access_tier?: string; free_tier_note?: string | null; pricing_url?: string | null;
  last_verified_at?: string; locked_base_url?: boolean; migration_guidance?: string | null;
  fields?: { key: string; label: string; required: boolean; type: string }[];
}
export interface ProviderConnection {
  catalog_id: string | null;
  id: string; organization_id: string; name: string; provider_type: ProviderType;
  base_url: string | null; enabled: boolean; has_secret: boolean;
  status: 'UNTESTED' | 'CONNECTED' | 'DEGRADED' | 'ERROR';
  last_tested_at: string | null; last_latency_ms: number | null; last_error_code: string | null;
  created_at: string; updated_at: string | null; model_count: number;
  config_json?: Record<string, unknown>;
}
export interface ConnectionInput {
  catalog_id: string;
  name: string; provider_type: ProviderType; base_url?: string | null; secret?: string; enabled?: boolean;
  config_json?: Record<string, unknown>;
}
export interface RegistryModel {
  provider_catalog_id: string | null;
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
  size_bytes?: number | null;
  context_tokens?: number | null; free?: boolean | null; reasoning?: boolean | null;
  deprecated?: boolean; recommended?: boolean; output_dimensions?: number[];
}
export interface OllamaRecommendation {
  model: string; display_name: string; tier: string; size_bytes: number; description: string; highlighted: boolean;
}
export interface OllamaPullJob {
  id: string; connection_id: string; model: string;
  status: 'QUEUED' | 'PULLING' | 'VERIFYING' | 'READY' | 'FAILED' | 'CANCELLED';
  completed_bytes: number; total_bytes: number; error_code: string | null; registered_model_id: string | null;
}
export interface ConnectionTest {
  status: string; latency_ms: number; capabilities: ProviderCapability[];
  discovery_supported: boolean; error_code: string | null;
}
export interface RerankBinding {
  model_id: string | null; candidate_limit: number; top_n: number; timeout_seconds: number;
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
  ollamaRecommendations(id: string) { return this.http.get<OllamaRecommendation[]>(`${this.base}/provider-connections/${id}/ollama/recommendations`); }
  pullOllama(id: string, model: string) { return this.http.post<OllamaPullJob>(`${this.base}/provider-connections/${id}/ollama/models/pull`, { model, register_after_pull: true }); }
  ollamaPull(id: string, job: string) { return this.http.get<OllamaPullJob>(`${this.base}/provider-connections/${id}/ollama/model-pulls/${job}`); }
  ollamaPulls(id: string) { return this.http.get<OllamaPullJob[]>(`${this.base}/provider-connections/${id}/ollama/model-pulls`); }
  register(id: string, payload: ModelInput) { return this.http.post<RegistryModel>(`${this.base}/provider-connections/${id}/models`, payload); }
  models(org: string) { return this.http.get<RegistryModel[]>(`${this.base}/organizations/${org}/models`); }
  workspaceModels(id: string, capability: ProviderCapability = 'EMBEDDING') { return this.http.get<RegistryModel[]>(`${this.base}/workspaces/${id}/models`, { params: { capability } }); }
  testModel(id: string) { return this.http.post<RegistryModel>(`${this.base}/models/${id}/test`, {}); }
  updateModel(id: string, enabled: boolean) { return this.http.patch<RegistryModel>(`${this.base}/models/${id}`, { enabled }); }
  removeModel(id: string) { return this.http.delete(`${this.base}/models/${id}`); }
  rerankBinding(id: string) { return this.http.get<RerankBinding>(`${this.base}/workspaces/${id}/rerank-model`); }
  bindRerank(id: string, payload: RerankBinding) { return this.http.put<RerankBinding>(`${this.base}/workspaces/${id}/rerank-model`, payload); }
}
