import { readFile, readdir, stat } from "node:fs/promises";
import { basename, dirname, join, relative, resolve } from "node:path";
import { homedir } from "node:os";

const DEFAULT_SESSION_KEY = "agent:main:main";
const TOOL_NAME = "claw-debug";

process.stdout.on("error", (error: NodeJS.ErrnoException) => {
  if (error.code === "EPIPE") {
    process.exit(0);
  }
  throw error;
});

type JsonObject = Record<string, unknown>;

type SessionSummary = {
  sessionId?: unknown;
  sessionFile?: unknown;
};

type ResolvedSession = {
  agentId: string;
  sessionKey: string;
  sessionsFile: string;
  summary: SessionSummary;
};

type DumpSection = {
  title: string;
  location: string;
  content?: string;
  missing?: boolean;
};

async function main(argv: string[]): Promise<number> {
  const [command, ...rest] = argv;

  if (command === undefined || command === "--help" || command === "-h") {
    printHelp();
    return command === undefined ? 1 : 0;
  }

  if (command !== "dump") {
    console.error(`error: unknown command '${command}'`);
    printHelp();
    return 2;
  }

  const sessionKey = rest[0] ?? DEFAULT_SESSION_KEY;
  if (rest.length > 1) {
    console.error("error: dump accepts at most one session key");
    return 2;
  }

  return dumpSession(sessionKey);
}

async function dumpSession(sessionKey: string): Promise<number> {
  const openclawHome = getOpenClawHome();
  const resolvedSession = await resolveSession(openclawHome, sessionKey);
  if (resolvedSession === null) {
    console.error(`error: session key not found: ${sessionKey}`);
    return 1;
  }

  const sections = await buildDumpSections(openclawHome, resolvedSession);
  for (const [index, section] of sections.entries()) {
    if (index > 0) {
      process.stdout.write("\n\n");
    }
    printSection(section);
  }

  return 0;
}

function getOpenClawHome(): string {
  const override = process.env.OPENCLAW_HOME;
  if (override !== undefined && override.trim() !== "") {
    return resolve(expandHome(override));
  }
  return join(homedir(), ".openclaw");
}

async function resolveSession(
  openclawHome: string,
  sessionKey: string,
): Promise<ResolvedSession | null> {
  const hintedAgentId = parseAgentId(sessionKey);
  if (hintedAgentId !== null) {
    const resolvedSession = await readSessionFromAgent(openclawHome, hintedAgentId, sessionKey);
    if (resolvedSession !== null) {
      return resolvedSession;
    }
  }

  const agentsDir = join(openclawHome, "agents");
  let entries: string[];
  try {
    entries = await readdir(agentsDir);
  } catch {
    return null;
  }

  for (const agentId of entries.sort()) {
    if (agentId === hintedAgentId) {
      continue;
    }
    const resolvedSession = await readSessionFromAgent(openclawHome, agentId, sessionKey);
    if (resolvedSession !== null) {
      return resolvedSession;
    }
  }

  return null;
}

function parseAgentId(sessionKey: string): string | null {
  const parts = sessionKey.split(":");
  if (parts.length >= 3 && parts[0] === "agent" && parts[1] !== "") {
    return parts[1];
  }
  return null;
}

async function readSessionFromAgent(
  openclawHome: string,
  agentId: string,
  sessionKey: string,
): Promise<ResolvedSession | null> {
  const sessionsFile = join(openclawHome, "agents", agentId, "sessions", "sessions.json");
  const payload = await readJson(sessionsFile);
  if (!isRecord(payload)) {
    return null;
  }

  const summary = payload[sessionKey];
  if (!isRecord(summary)) {
    return null;
  }

  return {
    agentId,
    sessionKey,
    sessionsFile,
    summary,
  };
}

async function buildDumpSections(
  openclawHome: string,
  resolvedSession: ResolvedSession,
): Promise<DumpSection[]> {
  const selectedSummary = {
    [resolvedSession.sessionKey]: resolvedSession.summary,
  };
  const sections: DumpSection[] = [
    {
      title: "session summary",
      location: resolvedSession.sessionsFile,
      content: `${JSON.stringify(selectedSummary, null, 2)}\n`,
    },
  ];

  const sessionFile = getSessionFile(openclawHome, resolvedSession);
  sections.push(await sectionFromFile("session logs", sessionFile));

  const sessionId = getString(resolvedSession.summary.sessionId) ?? sessionIdFromSessionFile(sessionFile);
  if (sessionId !== null) {
    const sessionDir = dirname(sessionFile);
    const trajectoryPointerFile = join(sessionDir, `${sessionId}.trajectory-path.json`);
    sections.push(await sectionFromFile("session trajectory summary", trajectoryPointerFile));

    const trajectoryPointer = await readJson(trajectoryPointerFile);
    const runtimeFile =
      isRecord(trajectoryPointer) && typeof trajectoryPointer.runtimeFile === "string"
        ? trajectoryPointer.runtimeFile
        : join(sessionDir, `${sessionId}.trajectory.jsonl`);
    sections.push(await sectionFromFile("session trajectory", runtimeFile));
  }

  const appServerFile = `${sessionFile}.codex-app-server.json`;
  sections.push(await sectionFromFile("codex app server", appServerFile));

  const appServer = await readJson(appServerFile);
  if (isRecord(appServer) && typeof appServer.threadId === "string") {
    const codexSessionFile = await findCodexSessionFile(
      openclawHome,
      resolvedSession.agentId,
      appServer.threadId,
    );
    if (codexSessionFile !== null) {
      sections.push(await sectionFromFile("codex session", codexSessionFile));
    } else {
      sections.push({
        title: "codex session",
        location: join(
          openclawHome,
          "agents",
          resolvedSession.agentId,
          "agent",
          "codex-home",
          "sessions",
          `**/*${appServer.threadId}.jsonl`,
        ),
        missing: true,
      });
    }
  }

  return sections;
}

function getSessionFile(openclawHome: string, resolvedSession: ResolvedSession): string {
  const fromSummary = getString(resolvedSession.summary.sessionFile);
  if (fromSummary !== null) {
    return expandHome(fromSummary);
  }

  const sessionId = getString(resolvedSession.summary.sessionId);
  if (sessionId !== null) {
    return join(openclawHome, "agents", resolvedSession.agentId, "sessions", `${sessionId}.jsonl`);
  }

  return join(openclawHome, "agents", resolvedSession.agentId, "sessions", "unknown-session.jsonl");
}

function sessionIdFromSessionFile(sessionFile: string): string | null {
  const name = basename(sessionFile);
  return name.endsWith(".jsonl") ? name.slice(0, -".jsonl".length) : null;
}

async function sectionFromFile(title: string, location: string): Promise<DumpSection> {
  const content = await readTextIfExists(location);
  if (content === null) {
    return { title, location, missing: true };
  }
  return { title, location, content };
}

function printSection(section: DumpSection): void {
  process.stdout.write(`# ${section.title}\n`);
  process.stdout.write(`# location: ${formatLocation(section.location)}\n`);
  if (section.missing === true) {
    process.stdout.write("[missing]\n");
    return;
  }
  if (section.content !== undefined) {
    process.stdout.write(section.content.endsWith("\n") ? section.content : `${section.content}\n`);
  }
}

async function readJson(path: string): Promise<unknown> {
  const text = await readTextIfExists(path);
  if (text === null) {
    return null;
  }
  try {
    return JSON.parse(text);
  } catch {
    return null;
  }
}

async function readTextIfExists(path: string): Promise<string | null> {
  try {
    return await readFile(path, "utf8");
  } catch {
    return null;
  }
}

async function findCodexSessionFile(
  openclawHome: string,
  agentId: string,
  threadId: string,
): Promise<string | null> {
  const root = join(openclawHome, "agents", agentId, "agent", "codex-home", "sessions");
  const matches: Array<{ path: string; mtimeMs: number }> = [];
  await collectFiles(root, (path) => basename(path).endsWith(`${threadId}.jsonl`), matches);
  matches.sort((left, right) => right.mtimeMs - left.mtimeMs || left.path.localeCompare(right.path));
  return matches[0]?.path ?? null;
}

async function collectFiles(
  root: string,
  predicate: (path: string) => boolean,
  matches: Array<{ path: string; mtimeMs: number }>,
): Promise<void> {
  let entries: string[];
  try {
    entries = await readdir(root);
  } catch {
    return;
  }

  for (const entry of entries) {
    const path = join(root, entry);
    let fileStat;
    try {
      fileStat = await stat(path);
    } catch {
      continue;
    }
    if (fileStat.isDirectory()) {
      await collectFiles(path, predicate, matches);
      continue;
    }
    if (fileStat.isFile() && predicate(path)) {
      matches.push({ path, mtimeMs: fileStat.mtimeMs });
    }
  }
}

function isRecord(value: unknown): value is JsonObject {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function getString(value: unknown): string | null {
  return typeof value === "string" && value !== "" ? value : null;
}

function expandHome(path: string): string {
  if (path === "~") {
    return homedir();
  }
  if (path.startsWith("~/")) {
    return join(homedir(), path.slice(2));
  }
  return path;
}

function formatLocation(path: string): string {
  const home = homedir();
  const absolute = resolve(path);
  const relativeToHome = relative(home, absolute);
  if (relativeToHome === "") {
    return "~";
  }
  if (!relativeToHome.startsWith("..")) {
    return `~/${relativeToHome}`;
  }
  return path;
}

function printHelp(): void {
  process.stdout.write(`Usage:
  ${TOOL_NAME} dump [session-key]

Commands:
  dump [session-key]  Dump OpenClaw session debug files. Defaults to ${DEFAULT_SESSION_KEY}.

Environment:
  OPENCLAW_HOME       Override the OpenClaw state root. Defaults to ~/.openclaw.
`);
}

void main(process.argv.slice(2)).then(
  (code) => {
    process.exitCode = code;
  },
  (error: unknown) => {
    console.error(`error: ${error instanceof Error ? error.message : String(error)}`);
    process.exitCode = 1;
  },
);
