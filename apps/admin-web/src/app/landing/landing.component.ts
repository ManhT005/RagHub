import { ChangeDetectionStrategy, Component } from '@angular/core';
import { RouterLink } from '@angular/router';
import { NzButtonModule } from 'ng-zorro-antd/button';
@Component({selector:'raghub-landing',imports:[RouterLink,NzButtonModule],templateUrl:'./landing.component.html',styleUrl:'./landing.component.css',changeDetection:ChangeDetectionStrategy.OnPush}) export class LandingComponent {}
