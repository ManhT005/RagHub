import { TestBed } from '@angular/core/testing';
import { ProviderLogoComponent } from './provider-logo.component';

describe('ProviderLogoComponent', () => {
  it('renders a local logo, falls back on error and recovers for another brand', () => {
    const fixture = TestBed.createComponent(ProviderLogoComponent);
    fixture.componentRef.setInput('catalogId', 'gemini');
    fixture.detectChanges();
    expect(fixture.nativeElement.getAttribute('aria-label')).toBe('Google Gemini');
    expect(fixture.nativeElement.querySelector('img').getAttribute('src')).toBe('assets/providers/google-gemini.svg');
    fixture.nativeElement.querySelector('img').dispatchEvent(new Event('error'));
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('G');
    fixture.componentRef.setInput('catalogId', 'compatible');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img').getAttribute('src')).toContain('openai-compatible.svg');
  });
  it('renders accessible initials for unknown brands with a fixed size', () => {
    const fixture = TestBed.createComponent(ProviderLogoComponent);
    fixture.componentRef.setInput('catalogId', 'missing');
    fixture.componentRef.setInput('size', 'sm');
    fixture.detectChanges();
    expect(fixture.nativeElement.querySelector('img')).toBeNull();
    expect(fixture.nativeElement.textContent).toContain('AI');
    expect(fixture.nativeElement.getAttribute('data-size')).toBe('sm');
  });
});
