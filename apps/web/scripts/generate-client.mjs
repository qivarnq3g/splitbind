import { mkdir, writeFile } from "node:fs/promises";
import { fileURLToPath } from "node:url";

import openapiTS, { astToString } from "openapi-typescript";

const schemaUrl = new URL("../../../contracts/openapi/schema.json", import.meta.url);
const outputUrl = new URL("../src/api/generated/schema.d.ts", import.meta.url);

await mkdir(fileURLToPath(new URL(".", outputUrl)), { recursive: true });
const nodes = await openapiTS(schemaUrl);
await writeFile(outputUrl, astToString(nodes), "utf8");
