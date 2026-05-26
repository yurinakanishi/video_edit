import { cp, mkdir, rm } from "node:fs/promises";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const appRoot = dirname(dirname(fileURLToPath(import.meta.url)));
const rendererSrc = join(appRoot, "src", "renderer");
const rendererDist = join(appRoot, "dist", "renderer");

await mkdir(rendererDist, { recursive: true });
await Promise.all([
	cp(join(rendererSrc, "index.html"), join(rendererDist, "index.html")),
	cp(join(rendererSrc, "styles.css"), join(rendererDist, "styles.css")),
]);

await rm(join(rendererDist, "renderer.js.map"), { force: true });
