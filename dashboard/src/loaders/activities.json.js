import { createReadStream } from "node:fs";
import { exportFile } from "./lib.js";

createReadStream(exportFile("activities.json")).pipe(process.stdout);
