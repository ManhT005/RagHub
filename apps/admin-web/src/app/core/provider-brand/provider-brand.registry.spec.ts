import { ProviderBrandService } from './provider-brand.service';
import { PROVIDER_BRANDS, shortModelName } from './provider-brand.registry';

describe('Provider brand registry', () => {
  it('keeps runtime-compatible brands separate', () => {
    const service = new ProviderBrandService();
    expect(service.resolve('gemini').logo).toContain('google-gemini.svg');
    expect(service.resolve('openai').logo).toContain('openai.svg');
    expect(service.resolve('compatible').logo).toContain('openai-compatible.svg');
    expect(service.resolve('compatible')).not.toEqual(service.resolve('openai'));
  });
  it('provides a fallback for every brand and unknown identity', () => {
    expect(Object.values(PROVIDER_BRANDS).every(brand => !!brand.fallback)).toBe(true);
    expect(new ProviderBrandService().resolve('unknown-brand').fallback).toBe('AI');
    expect(new ProviderBrandService().resolve(null).fallback).toBe('AI');
  });
  it('shortens model IDs only for display', () => {
    expect(shortModelName('sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2')).toBe('paraphrase-multilingual-MiniLM-L12-v2');
  });
});
