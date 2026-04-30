#!/usr/bin/env node
"use strict";

const { execSync, spawnSync } = require("child_process");
const path = require("path");
const fs = require("fs");

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
  log(`Using remote source: ${source}`);

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

  console.log(`
${GREEN}========================================${RESET}
  KNG plugin installed!
${GREEN}========================================${RESET}

  Available commands in Claude Code:

    /kng-init <project-id>          Initialize project KB
    /kng-test <feishu-url>          Generate test design
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
${CYAN}KNG — Knowledge-driven Next-Gen Test Agent${RESET}

Usage:
  npx github:WizardHeHeJun/kng install      Install the plugin into Claude Code
  npx github:WizardHeHeJun/kng uninstall    Remove the plugin from Claude Code
  npx github:WizardHeHeJun/kng help         Show this help message
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
