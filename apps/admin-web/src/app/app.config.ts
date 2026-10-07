import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideAnimationsAsync } from '@angular/platform-browser/animations/async';
import { provideRouter } from '@angular/router';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { LOCALE_ID } from '@angular/core';
import { registerLocaleData } from '@angular/common';
import localeVi from '@angular/common/locales/vi';
import {
  ApiOutline,
  CloudServerOutline,
  DashboardOutline,
  DatabaseOutline,
  FileSearchOutline,
  FileTextOutline,
  MessageOutline,
  RocketOutline,
  SettingOutline,
  TeamOutline,
} from '@ant-design/icons-angular/icons';
import { provideNzIcons } from 'ng-zorro-antd/icon';
import { provideNzI18n, vi_VN } from 'ng-zorro-antd/i18n';

import { routes } from './app.routes';
import { apiAuthInterceptor } from './core/api-auth.interceptor';

registerLocaleData(localeVi);

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    { provide: LOCALE_ID, useValue: 'vi' },
    provideAnimationsAsync(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([apiAuthInterceptor])),
    provideNzI18n(vi_VN),
    provideNzIcons([
      ApiOutline,
      DashboardOutline,
      DatabaseOutline,
      FileSearchOutline,
      FileTextOutline,
      MessageOutline,
      RocketOutline,
      SettingOutline,
      CloudServerOutline,
      TeamOutline,
    ]),
  ],
};
