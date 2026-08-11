/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require("fs");
const path = require("path");

const root = path.resolve(__dirname, "..");
const files = [];
function walk(dir) {
  for (const name of fs.readdirSync(dir)) {
    const full = path.join(dir, name);
    const stat = fs.statSync(full);
    if (stat.isDirectory() && !["node_modules", ".next"].includes(name)) walk(full);
    else if (/\.(tsx|jsx)$/.test(name)) files.push(full);
  }
}
walk(path.join(root, "app"));
walk(path.join(root, "components"));

const findings = [];
for (const file of files) {
  const text = fs.readFileSync(file, "utf8");
  const rel = path.relative(root, file);
  const imgs = [...text.matchAll(/<img\b([^>]*)>/g)];
  for (const match of imgs) {
    if (!/\balt\s*=/.test(match[1])) findings.push(`${rel}: <img> missing alt`);
  }
  const buttons = [...text.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)];
  for (const match of buttons) {
    const attrs = match[1], body = match[2].replace(/<[^>]+>/g, "").trim();
    if (!body && !/\baria-label\s*=/.test(attrs)) findings.push(`${rel}: icon-only button missing aria-label`);
  }
}
console.log(JSON.stringify({ files: files.length, findings }, null, 2));
if (findings.length) process.exitCode = 1;
