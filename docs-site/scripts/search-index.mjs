import { readdir, readFile, writeFile } from "node:fs/promises";
import { join, relative } from "node:path";

const root = new URL("../app/", import.meta.url).pathname;
const pages = [];
async function walk(directory) {
  for (const file of await readdir(directory, { withFileTypes: true })) {
    const path = join(directory, file.name);
    if (file.isDirectory()) await walk(path);
    else if (/^page\.(mdx|tsx)$/.test(file.name)) {
      const source = await readFile(path, "utf8");
      const route = `/${relative(root, directory)}`.replace(/\/$/, "") || "/";
      const title = route === "/" ? "Overview" : route === "/reference" ? "Python API" : source.match(/^# (.+)$/m)?.[1] ?? route.slice(1);
      let text = source.replace(/^export .+$/gm, "").replace(/<[^>]+>/g, " ").replace(/[#*`|{}]/g, " ").replace(/\s+/g, " ").trim();
      if (route === "/reference") {
        const reference = JSON.parse(await readFile(join(root, "reference.json"), "utf8"));
        text = reference.sections.flatMap((section) => section.names.map((item) => `${item.name}${item.signature} ${item.doc}`)).join(" ");
      }
      pages.push({ path: route, title, text });
    }
  }
}
await walk(root);
await writeFile(join(root, "search-index.json"), JSON.stringify(pages.sort((a, b) => a.path.localeCompare(b.path))));
console.log(`Indexed ${pages.length} documentation pages.`);
