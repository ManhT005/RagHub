import { ChangeDetectionStrategy, Component } from "@angular/core";
import { RouterLink, RouterLinkActive, RouterOutlet } from "@angular/router";
import { NzIconModule } from "ng-zorro-antd/icon";
import { NzLayoutModule } from "ng-zorro-antd/layout";
import { NzMenuModule } from "ng-zorro-antd/menu";
@Component({
  selector: "raghub-admin-layout",
  imports: [
    RouterLink,
    RouterLinkActive,
    RouterOutlet,
    NzIconModule,
    NzLayoutModule,
    NzMenuModule,
  ],
  templateUrl: "./admin-layout.component.html",
  styleUrl: "./admin-layout.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AdminLayoutComponent {}
