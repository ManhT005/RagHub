import { ProviderConnection } from './provider-api.service';

/** Only for connections created before catalog identity was persisted. */
export function resolveLegacyCatalogId(connection: Pick<ProviderConnection, 'provider_type' | 'base_url'>): string | null {
  if (connection.provider_type === 'OPENAI_COMPATIBLE') {
    return connection.base_url?.replace(/\/+$/, '') === 'https://api.openai.com/v1' ? 'openai' : 'compatible';
  }
  return ({ GOOGLE_GEMINI: 'gemini', OLLAMA: 'ollama', LOCAL_SENTENCE_TRANSFORMER: 'sentence-transformer' } as Record<string, string>)[connection.provider_type] ?? null;
}
