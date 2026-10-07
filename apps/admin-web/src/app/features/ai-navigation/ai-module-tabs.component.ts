import { ChangeDetectionStrategy, Component } from "@angular/core";
import { RouterLink, RouterLinkActive } from "@angular/router";
import { NzButtonModule } from "ng-zorro-antd/button";

@Component({
  selector: "raghub-ai-module-tabs",
  imports: [RouterLink, RouterLinkActive, NzButtonModule],
  template: `<nav class="ai-module-tabs" aria-label="AI & Models">
    <a nz-button class="module-tab" routerLink="/system/ai/providers" routerLinkActive="active" [routerLinkActiveOptions]="{ exact: true }">Providers</a>
    <a nz-button class="module-tab" routerLink="/system/ai/models" routerLinkActive="active">Model Registry</a>
    <a nz-button class="module-tab" routerLink="/system/ai/local" routerLinkActive="active">Local Models</a>
  </nav>`,
  styleUrl: "./ai-module-tabs.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiModuleTabsComponent {}
