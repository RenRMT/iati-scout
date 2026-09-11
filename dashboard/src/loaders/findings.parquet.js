import { createReadStream } from "node:fs";
import { exportFile } from "./lib.js";

createReadStream(exportFile("findings.parquet")).pipe(process.stdout);
