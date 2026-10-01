import { ChangeDetectionStrategy, Component, inject } from "@angular/core";
import { toSignal } from "@angular/core/rxjs-interop";
import { ActivatedRoute, RouterLink } from "@angular/router";
import { NzButtonModule } from "ng-zorro-antd/button";
import { PublicNavComponent } from "./public-nav.component";

@Component({
  selector: "raghub-public-page",
  imports: [PublicNavComponent, RouterLink, NzButtonModule],
  templateUrl: "./public-page.component.html",
  styleUrl: "./public-page.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PublicPageComponent {
  readonly routeData = toSignal(inject(ActivatedRoute).data);
}
