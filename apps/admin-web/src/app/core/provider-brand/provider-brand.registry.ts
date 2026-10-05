import { ProviderBrand } from './provider-brand.types';

export const PROVIDER_BRANDS: Record<string, ProviderBrand> = {
  gemini: { id: 'gemini', label: 'Google Gemini', logo: 'assets/providers/google-gemini.svg', fallback: 'G' },
  openai: { id: 'openai', label: 'OpenAI', logo: 'assets/providers/openai.svg', fallback: 'O' },
  compatible: { id: 'compatible', label: 'OpenAI-compatible', logo: 'assets/providers/openai-compatible.svg', fallback: 'API' },
  ollama: { id: 'ollama', label: 'Ollama', logo: 'assets/providers/ollama.svg', fallback: 'O' },
  'sentence-transformer': { id: 'sentence-transformer', label: 'Sentence Transformer', logo: 'assets/providers/local-embedding.svg', fallback: 'ST' },
  anthropic: { id: 'anthropic', label: 'Anthropic', logo: 'assets/providers/anthropic.svg', fallback: 'A' },
  'azure-openai': { id: 'azure-openai', label: 'Azure OpenAI', logo: null, fallback: 'AZ', genericFallback: true },
  nvidia: { id: 'nvidia', label: 'NVIDIA', logo: 'assets/providers/nvidia.svg', fallback: 'N' },
  deepseek: { id: 'deepseek', label: 'DeepSeek', logo: 'assets/providers/deepseek.svg', fallback: 'D' },
  groq: { id: 'groq', label: 'Groq', logo: null, fallback: 'GQ', genericFallback: true },
  cloudflare: { id: 'cloudflare', label: 'Cloudflare', logo: 'assets/providers/cloud-generic.svg', fallback: 'CF', genericFallback: true },
};
export const UNKNOWN_PROVIDER_BRAND: ProviderBrand = { id: 'unknown', label: 'AI provider', logo: null, fallback: 'AI', genericFallback: true };

export function shortModelName(model: string): string {
  return model.split('/').filter(Boolean).pop() || model;
}
