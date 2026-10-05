export interface ProviderBrand {
  id: string;
  label: string;
  logo: string | null;
  fallback: string;
  genericFallback?: boolean;
}
