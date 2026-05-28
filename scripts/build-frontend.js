const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const source = path.join(root, "frontend");
const dist = path.join(root, "dist");
const apiBaseUrl = process.env.LMS_API_URL || process.env.VITE_API_URL || "";

fs.rmSync(dist, { recursive: true, force: true });
fs.mkdirSync(dist, { recursive: true });

for (const entry of fs.readdirSync(source)) {
  fs.copyFileSync(path.join(source, entry), path.join(dist, entry));
}

fs.writeFileSync(
  path.join(dist, "config.js"),
  `window.LMS_CONFIG = ${JSON.stringify({ apiBaseUrl })};\n`,
  "utf8"
);
