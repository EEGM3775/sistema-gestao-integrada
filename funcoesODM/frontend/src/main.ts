// CRITICAL: Define global BEFORE any imports
// This is required for sockjs-client and other Node.js libraries
(window as any).global = window;
(window as any).process = (window as any).process || { env: {}, browser: true };
(window as any).Buffer = (window as any).Buffer || { isBuffer: () => false };

import { bootstrapApplication } from '@angular/platform-browser';
import { appConfig } from './app/app.config';
import { AppComponent } from './app/app.component';

bootstrapApplication(AppComponent, appConfig)
  .catch((err) => console.error(err));
