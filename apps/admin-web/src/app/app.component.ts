import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthSessionService } from './core/auth-session.service';
import { SetupStateService } from './setup/setup-state.service';

@Component({
  selector: 'raghub-root',
  imports: [RouterOutlet],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent {
  protected readonly auth = inject(AuthSessionService);
  protected readonly setup = inject(SetupStateService);
  protected retrySession(): void { window.location.reload(); }
}
