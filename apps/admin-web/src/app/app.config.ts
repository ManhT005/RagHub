import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import {
  CloudServerOutline,
  DashboardOutline,
  DatabaseOutline,
  FileTextOutline,
  MessageOutline,
} from '@ant-design/icons-angular/icons';
import { provideNzIcons } from 'ng-zorro-antd/icon';

import { routes } from './app.routes';
import { apiAuthInterceptor } from './core/api-auth.interceptor';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideAnimationsAsync(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([apiAuthInterceptor])),
    provideNzIcons([
      DashboardOutline,
      DatabaseOutline,
      FileTextOutline,
      MessageOutline,
      CloudServerOutline,
    ]),
  ],
};
