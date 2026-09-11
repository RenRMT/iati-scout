import { createReadStream } from "node:fs";
import { exportFile } from "./lib.js";

createReadStream(exportFile("meta.json")).pipe(process.stdout);
