import { mkdirSync, copyFileSync } from 'node:fs';
mkdirSync('public/widget', { recursive: true });
copyFileSync('../chat-widget/public/raghub.js', 'public/widget/raghub.js');
