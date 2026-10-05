import { Injectable } from '@angular/core';
import { PROVIDER_BRANDS, UNKNOWN_PROVIDER_BRAND } from './provider-brand.registry';

@Injectable({ providedIn: 'root' })
export class ProviderBrandService {
  resolve(catalogId: string | null | undefined) {
    return catalogId ? PROVIDER_BRANDS[catalogId] ?? UNKNOWN_PROVIDER_BRAND : UNKNOWN_PROVIDER_BRAND;
  }
}
