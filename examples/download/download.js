#!/usr/bin/env node
// download: the same pattern in JavaScript, with no library.
//
//     node download.js            run three made-up downloads and print each move
//     node download.js --shape    print the table as JSON, which is what shape reads
//
// shape reads JSON, so a program in any language can be shown. The program keeps its
// moves in one table (MOVES), takes every move by looking it up there (step), and
// prints that same table in shape's format (toShape).

const isMissing = {
  name: "isMissing",
  says: "The server answered that the file does not exist.",
  test: (job) => job.server === "missing",
};

const canRetry = {
  name: "canRetry",
  says: "The connection dropped, and fewer than three tries have been made.",
  test: (job) => job.tries < 3,
};

// One line is one move: in the state "from", on the event "on", go to the state "to".
const MOVES = [
  { id: "start",      from: "idle",       on: "requested",  to: "connecting" },
  { id: "connected",  from: "connecting", on: "connected",  to: "receiving" },
  { id: "missing",    from: "connecting", on: "error",      to: "not_found", when: isMissing },
  { id: "retry",      from: "connecting", on: "error",      to: "connecting", when: canRetry, does: "wait" },
  { id: "gave_up",    from: "connecting", on: "error",      to: "failed" },
  { id: "received",   from: "receiving",  on: "complete",   to: "verifying" },
  { id: "verified",   from: "verifying",  on: "sum_matches", to: "saved", does: "move_into_place" },
  { id: "corrupt",    from: "verifying",  on: "sum_differs", to: "failed", does: "delete_partial_file" },
];

const MACHINE = {
  id: "download.fetch",
  about: "Fetches one file: connects, receives it, checks it and saves it.",
  initial: "idle",
  goal: "saved",
  attention: ["not_found", "failed"],
};

// The move the table gives for this state and event: the first one whose condition holds.
function step(state, event, job) {
  const move = MOVES.find((m) => m.from === state && m.on === event && (!m.when || m.when.test(job)));
  if (!move) throw new Error("no move from " + state + " on " + event);
  return move;
}

// The table in shape's format: states, then the events of each, then the branches in order.
function toShape() {
  const states = {};
  for (const m of MOVES) {
    for (const s of [m.from, m.to]) states[s] = states[s] || { on: {} };
  }
  for (const m of MOVES) {
    const branch = { id: m.id, target: m.to };
    if (m.when) branch.guard = { name: m.when.name, says: m.when.says };
    if (m.does) branch.actions = [m.does];
    (states[m.from].on[m.on] = states[m.from].on[m.on] || []).push(branch);
  }
  return Object.assign({}, MACHINE, { defined_in: "download/download.js", states });
}

// The work of each state: do it, then say what happened.
const WORK = {
  idle: () => "requested",
  connecting: (job) => { job.tries += 1; return job.server === "up" || (job.server === "flaky" && job.tries > 1) ? "connected" : "error"; },
  receiving: () => "complete",
  verifying: (job) => (job.intact ? "sum_matches" : "sum_differs"),
};

function fetchFile(job) {
  let state = MACHINE.initial;
  while (WORK[state]) {
    const event = WORK[state](job);
    const move = step(state, event, job);
    console.log("    " + state.padEnd(11) + event.padEnd(12) + " -> " + move.to);
    state = move.to;
  }
  return state;
}

if (process.argv.includes("--shape")) {
  console.log(JSON.stringify(toShape(), null, 2));
} else {
  const jobs = [
    ["a file from a server that drops the first connection", { server: "flaky", intact: true }],
    ["a file the server does not have", { server: "missing", intact: true }],
    ["a file that arrives damaged", { server: "up", intact: false }],
  ];
  for (const [name, job] of jobs) {
    console.log(name);
    console.log("    ends in " + fetchFile(Object.assign({ tries: 0 }, job)));
  }
}
