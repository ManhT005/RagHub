import { mkdir, readdir, copyFile } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const source = resolve(root, 'assets/providers');
const staging = resolve(root, 'apps/admin-web/.provider-assets');
await mkdir(staging, { recursive: true });
for (const file of await readdir(source, { withFileTypes: true })) {
  if (file.isFile() && file.name.endsWith('.svg')) await copyFile(resolve(source, file.name), resolve(staging, file.name));
}
console.log('Provider assets staged from the shared assets/providers directory.');
