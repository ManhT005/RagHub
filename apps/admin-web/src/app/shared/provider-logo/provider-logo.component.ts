import { ChangeDetectionStrategy, Component, computed, inject, input, signal } from '@angular/core';
import { ProviderBrandService } from '../../core/provider-brand/provider-brand.service';

@Component({
  selector: 'raghub-provider-logo',
  templateUrl: './provider-logo.component.html',
  styleUrl: './provider-logo.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { '[attr.data-size]': 'size()', '[attr.aria-label]': 'brand().label', 'role': 'img' },
})
export class ProviderLogoComponent {
  readonly catalogId = input<string | null | undefined>(null);
  readonly size = input<'sm' | 'md' | 'lg'>('md');
  private readonly brands = inject(ProviderBrandService);
  protected readonly brand = computed(() => this.brands.resolve(this.catalogId()));
  protected readonly failedAsset = signal<string | null>(null);
  protected readonly showImage = computed(() => !!this.brand().logo && this.failedAsset() !== this.brand().logo);
}
