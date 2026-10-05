import { readFile, readdir, access } from 'node:fs/promises';
import { resolve, dirname } from 'node:path';
import { fileURLToPath } from 'node:url';
import { createRequire } from 'node:module';

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const app = resolve(root, 'apps/admin-web');
const require = createRequire(resolve(app, 'package.json'));
const ts = require('typescript');
const registrySource = await readFile(resolve(app, 'src/app/core/provider-brand/provider-brand.registry.ts'), 'utf8');
const { outputText } = ts.transpileModule(registrySource, { compilerOptions: { module: ts.ModuleKind.ESNext } });
const { PROVIDER_BRANDS } = await import(`data:text/javascript;base64,${Buffer.from(outputText).toString('base64')}`);
const catalog = await readFile(resolve(root, 'backend/app/modules/ai_providers/catalog.py'), 'utf8');
const ids = [...catalog.matchAll(/id="([^"]+)"/g)].map(match => match[1]);
const comingSoon = catalog.match(/for name in \(([\s\S]*?)\)/)?.[1];
if (!comingSoon || ids.length === 0) throw new Error('Catalog format changed; update the brand checker to read all IDs.');
ids.push(...[...comingSoon.matchAll(/"([^"]+)"/g)].map(match => match[1].toLowerCase().replaceAll(' ', '-')));
for (const id of ids) {
  const brand = PROVIDER_BRANDS[id];
  if (!brand?.fallback) throw new Error(`Missing brand/fallback for catalog item ${id}`);
  if (!brand.logo && !brand.genericFallback) throw new Error(`Missing asset or explicit fallback for ${id}`);
  if (brand.logo) {
    if (!brand.logo.startsWith('assets/providers/')) throw new Error(`Nonlocal logo: ${id}`);
    await access(resolve(root, brand.logo));
  }
}
async function checkTemplates(directory) {
  for (const entry of await readdir(directory, { withFileTypes: true })) {
    const path = resolve(directory, entry.name);
    if (entry.isDirectory()) await checkTemplates(path);
    else if (/\.(html|ts)$/.test(entry.name)) {
      const source = await readFile(path, 'utf8');
      if (/<img\b[^>]*\bsrc\s*=\s*["'](?:https?:)?\/\//i.test(source)) throw new Error(`Remote image in ${path}`);
    }
  }
}
await checkTemplates(resolve(app, 'src/app'));
console.log(`PASS: ${ids.length} provider brands have local assets or explicit fallbacks; no remote images.`);
