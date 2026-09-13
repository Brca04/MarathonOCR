/**
 * Saves the race emblem next to the app so a deployment does not hotlink the
 * official site. Run it on a machine with network access:
 *
 *   npm run fetch:brand
 *
 * then set NEXT_PUBLIC_BRAND_MARK=/brand/znak.jpg and
 * NEXT_PUBLIC_BRAND_ICON=/brand/znak-150.jpg in .env.local.
 */
import { mkdir, writeFile } from 'node:fs/promises';

const FILES = [
  ['https://www.zagreb-marathon.com/wp-content/uploads/znak.jpg', 'public/brand/znak.jpg'],
  ['https://www.zagreb-marathon.com/wp-content/uploads/znak-150x150.jpg', 'public/brand/znak-150.jpg'],
];

await mkdir('public/brand', { recursive: true });
for (const [url, dest] of FILES) {
  const res = await fetch(url);
  if (!res.ok) {
    console.error(`${url} -> ${res.status}`);
    process.exitCode = 1;
    continue;
  }
  await writeFile(dest, Buffer.from(await res.arrayBuffer()));
  console.log(`${dest} <- ${url}`);
}
