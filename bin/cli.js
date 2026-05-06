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

  // Step 1: Add marketplace
  log("Adding KNG marketplace...");
  const addResult = runClaude(`plugin marketplace add "${source}"`);
  if (addResult.ok) {
    success("Marketplace added.");
  } else {
    if (addResult.output.includes("already")) {
      warn("Marketplace already registered, updating...");
      runClaude(`plugin marketplace update ${MARKETPLACE_ID}`);
    } else {
      warn(`Marketplace add returned: ${addResult.output}`);
      log("Trying to continue with installation...");
    }
  }

  // Step 2: Install plugin
  log("Installing kng plugin...");
  const installResult = runClaude(`plugin install ${PLUGIN_NAME}@${MARKETPLACE_ID}`);
  if (installResult.ok) {
    success("Plugin installed successfully!");
  } else {
    if (installResult.output.includes("already installed")) {
      warn("Plugin already installed.");
    } else {
      warn(`Plugin install returned: ${installResult.output}`);
    }
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

function showHelp() {
  console.log(`
${CYAN}KNG — Knowledge-driven Generator${RESET}

Usage:
  kng-plugin install      Install the plugin into Claude Code
  kng-plugin uninstall    Remove the plugin from Claude Code
  kng-plugin help         Show this help message

Quick install:
  npx kng-plugin install

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
