#!/usr/bin/env node
"use strict";

const { execSync, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");
const os = require("os");

const PLUGIN_NAME = "kng";
const REPO_URL = "https://github.com/WizardHeHeJun/kng.git";
const PACKAGE_ROOT = path.resolve(__dirname, "..");
const MARKETPLACE_ID = "kng-marketplace";

const CYAN = "\x1b[36m";
const GREEN = "\x1b[32m";
const RED = "\x1b[31m";
const YELLOW = "\x1b[33m";
const RESET = "\x1b[0m";

function log(msg) {
  console.log(`${CYAN}[kng]${RESET} ${msg}`);
}
function success(msg) {
  console.log(`${GREEN}[kng]${RESET} ${msg}`);
}
function warn(msg) {
  console.log(`${YELLOW}[kng]${RESET} ${msg}`);
}
function error(msg) {
  console.error(`${RED}[kng]${RESET} ${msg}`);
}

function getKngHome() {
  return process.env.KNG_HOME || path.join(os.homedir(), ".kng-plugin");
}

function scaffoldKngHome() {
  const kngHome = getKngHome();
  log(`Setting up data directory: ${kngHome}\n`);

  fs.mkdirSync(path.join(kngHome, "kb", "capability"), { recursive: true });
  fs.mkdirSync(path.join(kngHome, "kb", "projects"), { recursive: true });

  const configPath = path.join(kngHome, "kng.config.json");
  if (!fs.existsSync(configPath)) {
    const config = {
      active_project: "",
      kb_root: path.join(kngHome, "kb").replace(/\\/g, "/"),
      output_dir: "./test-output",
      db_path: path.join(kngHome, "kng.db").replace(/\\/g, "/"),
    };
    fs.writeFileSync(configPath, JSON.stringify(config, null, 2) + "\n");
    success(`Created config: ${configPath}`);
  } else {
    warn("Config already exists, skipping.");
  }

  success(`Data directory ready: ${kngHome}\n`);
}

function findClaude() {
  const result = spawnSync(
    process.platform === "win32" ? "where" : "which",
    ["claude"],
    { stdio: "pipe", encoding: "utf-8" }
  );
  return result.status === 0;
}

function runClaude(args) {
  try {
    const result = execSync(`claude ${args}`, {
      stdio: "pipe",
      encoding: "utf-8",
      timeout: 30000,
    });
    return { ok: true, output: result.trim() };
  } catch (e) {
    return { ok: false, output: e.stderr || e.message };
  }
}

function getClaudePluginDir() {
  return path.join(os.homedir(), ".claude", "plugins");
}

function cleanMarketplaceCache() {
  const pluginDir = getClaudePluginDir();
  const dirs = [
    path.join(pluginDir, "cache", MARKETPLACE_ID),
    path.join(pluginDir, "marketplaces", MARKETPLACE_ID),
  ];
  for (const dir of dirs) {
    if (fs.existsSync(dir)) {
      fs.rmSync(dir, { recursive: true, force: true });
    }
  }
}

function install() {
  log("Installing KNG plugin for Claude Code...\n");

  if (!findClaude()) {
    error("Claude Code CLI not found.");
    console.log(`
  Please install Claude Code first:
    npm install -g @anthropic-ai/claude-code
    `);
    process.exit(1);
  }

  success("Claude Code CLI detected.\n");

  const source = REPO_URL;
  log(`Using source: ${source}`);

  // Step 1: Clean old installation to ensure latest version
  const checkResult = runClaude(`plugin marketplace list`);
  const alreadyInstalled = checkResult.ok && checkResult.output.includes(MARKETPLACE_ID);

  if (alreadyInstalled) {
    log("Refreshing existing installation...");
    runClaude(`plugin uninstall ${PLUGIN_NAME} 2>/dev/null`);
    runClaude(`plugin marketplace remove ${MARKETPLACE_ID}`);
    cleanMarketplaceCache();
    success("Old version cleaned.");
  }

  // Step 2: Add marketplace (fresh clone from GitHub)
  log("Adding KNG marketplace...");
  const addResult = runClaude(`plugin marketplace add "${source}"`);
  if (addResult.ok) {
    success("Marketplace added.");
  } else {
    warn(`Marketplace add returned: ${addResult.output}`);
    log("Trying to continue with installation...");
  }

  // Step 3: Install plugin
  log("Installing kng plugin...");
  const installResult = runClaude(`plugin install ${PLUGIN_NAME}@${MARKETPLACE_ID}`);
  if (installResult.ok) {
    success("Plugin installed successfully!");
  } else {
    warn(`Plugin install returned: ${installResult.output}`);
  }

  // Step 3: Scaffold data directory
  scaffoldKngHome();

  const kngHome = getKngHome();
  console.log(`
${GREEN}========================================${RESET}
  KNG plugin installed!
${GREEN}========================================${RESET}

  Data directory: ${CYAN}${kngHome}${RESET}
  Override with:  KNG_HOME=/custom/path kng-plugin install

  Available commands in Claude Code:

    /kng-init <project-id>          Initialize project KB
    /kng-kb list|add|import         Manage knowledge base
    /kng-evolve                     Feedback & learning
    /kng-select <project-id>        Switch project

  Quick start:
    /kng-init my-game --from-lark <url>

  Run ${CYAN}/reload-plugins${RESET} in Claude Code to activate.
`);
}

function uninstall() {
  log("Uninstalling KNG plugin...\n");

  if (!findClaude()) {
    error("Claude Code CLI not found.");
    process.exit(1);
  }

  const result = runClaude(`plugin uninstall ${PLUGIN_NAME}@${MARKETPLACE_ID}`);
  if (result.ok) {
    success("Plugin uninstalled.");
  } else {
    warn(result.output);
  }

  const rmResult = runClaude(`plugin marketplace remove ${MARKETPLACE_ID}`);
  if (rmResult.ok) {
    success("Marketplace removed.");
  } else {
    warn(rmResult.output);
  }

  success("KNG plugin removed.");
}

// ── Skill Management ──

function getCapabilityDir() {
  const dir = path.join(getKngHome(), "kb", "capability");
  fs.mkdirSync(dir, { recursive: true });
  return dir;
}

function getInstalledSkills() {
  const dir = getCapabilityDir();
  try {
    return fs.readdirSync(dir).filter((f) => f.endsWith(".md"));
  } catch {
    return [];
  }
}

function downloadFile(url, destPath) {
  const script = [
    "const https=require('https'),http=require('http'),fs=require('fs');",
    "function get(u,r){if(r>5){process.exit(1);}",
    "const mod=u.startsWith('https')?https:http;",
    "mod.get(u,{headers:{'User-Agent':'kng-plugin'}},res=>{",
    "if(res.statusCode>=300&&res.statusCode<400&&res.headers.location){",
    "let loc=res.headers.location;",
    "if(loc.startsWith('/'))loc=new URL(u).origin+loc;",
    "get(loc,r+1);}",
    "else if(res.statusCode===200){",
    "const chunks=[];res.on('data',c=>chunks.push(c));",
    "res.on('end',()=>{fs.writeFileSync(process.argv[2],Buffer.concat(chunks));process.exit(0);});}",
    "else{process.exit(1);}",
    "}).on('error',()=>process.exit(1));}",
    "get(process.argv[1],0);",
  ].join("");

  const result = spawnSync("node", ["-e", script, url, destPath], {
    timeout: 30000,
    stdio: "pipe",
  });
  if (result.status !== 0) {
    throw new Error("Download failed" + (result.stderr ? ": " + result.stderr.toString().trim() : ""));
  }
}

function refreshRegistry() {
  const capDir = getCapabilityDir();
  const scriptPath = path.join(PACKAGE_ROOT, "kng-plugin", "scripts", "generate_registry.py");
  if (!fs.existsSync(scriptPath)) {
    return;
  }
  try {
    execSync(`python "${scriptPath}" "${capDir}"`, {
      stdio: "pipe",
      encoding: "utf-8",
      timeout: 15000,
    });
  } catch {
    warn("Could not refresh registry (python may not be installed).");
  }
}

function skillList() {
  const installed = getInstalledSkills();
  const capDir = getCapabilityDir();

  console.log(`\n${CYAN}Installed Skills${RESET} (${capDir})\n`);

  if (installed.length === 0) {
    console.log(`  (empty)\n`);
    console.log(`  Install skills from:`);
    console.log(`    URL:    ${CYAN}npx kng-plugin skill install <url>${RESET}`);
    console.log(`    File:   ${CYAN}npx kng-plugin skill install <path.md>${RESET}`);
    console.log(`    Feishu: ${CYAN}npx kng-plugin skill install --from-lark <url>${RESET}\n`);
    return;
  }

  for (const filename of installed.sort()) {
    const filePath = path.join(capDir, filename);
    const name = filename.replace(/\.md$/, "");
    let title = name;
    try {
      const head = fs.readFileSync(filePath, "utf-8").slice(0, 500);
      const match = head.match(/^#\s+(.+)/m);
      if (match) title = match[1].trim();
    } catch {}
    console.log(`  ${name.padEnd(32)} ${title}`);
  }

  console.log(`\n  Total: ${installed.length} skill(s)\n`);
}

function installFromUrl(url) {
  let filename;
  try {
    const urlPath = new URL(url).pathname;
    filename = path.basename(urlPath);
  } catch {
    filename = "downloaded-skill.md";
  }
  if (!filename.endsWith(".md")) {
    filename = filename + ".md";
  }

  const destPath = path.join(getCapabilityDir(), filename);
  log(`Downloading from URL: ${url}`);

  try {
    downloadFile(url, destPath);
    success(`Installed: ${filename}`);
    refreshRegistry();
  } catch (e) {
    error(`Failed to download: ${e.message}`);
  }
}

function installFromLocalFile(filePath) {
  const absPath = path.resolve(filePath);
  if (!fs.existsSync(absPath)) {
    error(`File not found: ${absPath}`);
    return;
  }
  const filename = path.basename(absPath);
  const destPath = path.join(getCapabilityDir(), filename);

  log(`Copying from local file: ${absPath}`);
  fs.copyFileSync(absPath, destPath);
  success(`Installed: ${filename}`);
  refreshRegistry();
}

function installFromLark(url) {
  warn("Feishu/Lark import requires the lark-cli skill inside Claude Code.\n");
  console.log(`  Run the following command inside Claude Code:\n`);
  console.log(`    ${CYAN}/kng-kb import --type capability --from-lark ${url}${RESET}\n`);
  console.log(`  This will fetch the document and install it as a capability skill.\n`);
}

function skillInstall(args) {
  if (args.length === 0) {
    error("No source specified.");
    console.log(`  Usage: kng-plugin skill install <url|path.md> [--from-lark <url>]`);
    process.exit(1);
  }

  const larkIdx = args.indexOf("--from-lark");
  if (larkIdx !== -1) {
    const larkUrl = args[larkIdx + 1];
    if (!larkUrl) {
      error("Missing URL after --from-lark");
      process.exit(1);
    }
    return installFromLark(larkUrl);
  }

  const positional = args.filter((a) => !a.startsWith("--"));

  for (const source of positional) {
    if (source.startsWith("http://") || source.startsWith("https://")) {
      installFromUrl(source);
    } else {
      installFromLocalFile(source);
    }
  }
}

function skillRemove(args) {
  if (args.length === 0) {
    error("No skill name specified.");
    console.log(`  Usage: kng-plugin skill remove <name>`);
    process.exit(1);
  }

  const name = args[0];
  const capDir = getCapabilityDir();
  const filename = name.endsWith(".md") ? name : name + ".md";
  const filePath = path.join(capDir, filename);

  if (!fs.existsSync(filePath)) {
    error(`Skill "${name}" is not installed.`);
    const installed = getInstalledSkills();
    const matches = [...installed].filter((f) => f.includes(name));
    if (matches.length > 0) {
      console.log(`  Matching installed skills: ${matches.join(", ")}`);
    }
    return;
  }

  fs.unlinkSync(filePath);
  success(`Removed: ${filename}`);
  refreshRegistry();
}

function skillHelp() {
  console.log(`
${CYAN}KNG Skill Manager${RESET}

Usage:
  kng-plugin skill list                        List installed skills
  kng-plugin skill install <url>               Install from HTTP URL
  kng-plugin skill install <path.md>           Install from local file
  kng-plugin skill install --from-lark <url>   Import from Feishu (via Claude Code)
  kng-plugin skill remove <name>               Remove an installed skill

Examples:
  kng-plugin skill install https://example.com/my-skill.md
  kng-plugin skill install ./custom-skill.md
  kng-plugin skill install --from-lark https://xxx.feishu.cn/wiki/xxx
  kng-plugin skill remove my-skill
`);
}

function skillCommand(args) {
  const subCmd = args[0];
  switch (subCmd) {
    case "list":
      return skillList();
    case "install":
      return skillInstall(args.slice(1));
    case "remove":
      return skillRemove(args.slice(1));
    default:
      return skillHelp();
  }
}

// ── Help ──

function showHelp() {
  console.log(`
${CYAN}KNG — Knowledge-driven Generator${RESET}

Usage:
  kng-plugin install                   Install the plugin into Claude Code
  kng-plugin uninstall                 Remove the plugin from Claude Code
  kng-plugin skill list                List installed capability skills
  kng-plugin skill install <url>       Install skill from URL
  kng-plugin skill install <file.md>   Install skill from local file
  kng-plugin skill remove <name>       Remove a skill from capability KB
  kng-plugin help                      Show this help message

Data directory: ~/.kng-plugin/ (override with KNG_HOME env var)
`);
}

// ── Main ──
const command = process.argv[2] || "help";

switch (command) {
  case "install":
    install();
    break;
  case "uninstall":
    uninstall();
    break;
  case "skill":
    skillCommand(process.argv.slice(3));
    break;
  case "help":
  case "--help":
  case "-h":
    showHelp();
    break;
  default:
    error(`Unknown command: ${command}`);
    showHelp();
    process.exit(1);
}
