import { createReadStream } from "node:fs";
import { exportFile } from "./lib.js";

createReadStream(exportFile("summary.json")).pipe(process.stdout);
