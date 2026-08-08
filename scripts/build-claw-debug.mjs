#!/usr/bin/env node
import { chmod, mkdir, readFile, rm, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";

const root = resolve(new URL("..", import.meta.url).pathname);
const built = resolve(root, ".build/claw-debug.js");
const target = resolve(root, "tools/claw-debug/bin/claw-debug");

const generated = await readFile(built, "utf8");
const withShebang = generated.startsWith("#!")
  ? generated
  : `#!/usr/bin/env node\n${generated}`;

await mkdir(dirname(target), { recursive: true });
await writeFile(target, withShebang, "utf8");
await chmod(target, 0o755);
await rm(resolve(root, ".build"), { recursive: true, force: true });
