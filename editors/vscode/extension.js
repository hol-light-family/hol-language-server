// VS Code client for the hol-language-server command. It starts the server over
// stdio for .ml and .hl files. It declares no language: syntax highlighting
// comes from vscode-hol-light or an OCaml extension.

const vscode = require("vscode");
const { LanguageClient } = require("vscode-languageclient/node");

let client;
let outputChannel;
// Restarts run one at a time: a client that is still starting cannot be
// stopped, so overlapping restarts would leave two servers running.
let queue = Promise.resolve();

function serverOptions() {
  const config = vscode.workspace.getConfiguration("holLanguageServer");
  return {
    command: config.get("command", "hol-language-server"),
    args: config.get("args", []),
  };
}

function createClient() {
  const server = serverOptions();
  return new LanguageClient(
    "hol-language-server",
    "HOL Light Language Server Protocol",
    { run: server, debug: server },
    {
      documentSelector: [{ scheme: "file", pattern: "**/*.{ml,hl}" }],
      // One channel for every client, or each restart adds another.
      outputChannel,
    },
  );
}

async function stopClient() {
  const old = client;
  client = undefined;
  // stop() throws unless the client is running, as after a failed start.
  if (old && old.isRunning()) {
    await old.stop();
  }
}

function report(error) {
  vscode.window.showErrorMessage(`HOL language server: ${error.message}`);
}

function restart() {
  queue = queue
    .then(async () => {
      await stopClient();
      client = createClient();
      await client.start();
    })
    .catch(report);
  return queue;
}

function activate(context) {
  outputChannel = vscode.window.createOutputChannel("HOL Light Language Server Protocol");
  context.subscriptions.push(
    outputChannel,
    vscode.commands.registerCommand("holLanguageServer.restart", restart),
    vscode.workspace.onDidChangeConfiguration((event) => {
      if (event.affectsConfiguration("holLanguageServer")) {
        restart();
      }
    }),
  );
  return restart();
}

function deactivate() {
  queue = queue.then(stopClient);
  return queue;
}

module.exports = { activate, deactivate };
