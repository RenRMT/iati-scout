import { createReadStream } from "node:fs";
import { exportFile } from "./lib.js";

createReadStream(exportFile("rules.json")).pipe(process.stdout);
