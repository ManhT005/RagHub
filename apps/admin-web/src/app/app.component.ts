import { ChangeDetectionStrategy, Component, inject } from '@angular/core';
import { RouterOutlet } from '@angular/router';
import { AuthSessionService } from './core/auth-session.service';

@Component({
  selector: 'raghub-root',
  imports: [RouterOutlet],
  templateUrl: './app.component.html',
  styleUrl: './app.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AppComponent {
  protected readonly auth = inject(AuthSessionService);
  protected retrySession(): void { window.location.reload(); }
}
