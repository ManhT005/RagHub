import { ChangeDetectionStrategy, Component } from "@angular/core";
import { RouterLink } from "@angular/router";
import {
  ApiOutline,
  FileSearchOutline,
  FileTextOutline,
  RocketOutline,
} from "@ant-design/icons-angular/icons";
import { NzButtonModule } from "ng-zorro-antd/button";
import { NzIconModule, provideNzIconsPatch } from "ng-zorro-antd/icon";
import { PublicNavComponent } from "./public-nav.component";
@Component({
  selector: "raghub-landing",
  imports: [RouterLink, NzButtonModule, NzIconModule, PublicNavComponent],
  providers: [
    provideNzIconsPatch([
      ApiOutline,
      FileSearchOutline,
      FileTextOutline,
      RocketOutline,
    ]),
  ],
  templateUrl: "./landing.component.html",
  styleUrl: "./landing.component.css",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class LandingComponent {}
