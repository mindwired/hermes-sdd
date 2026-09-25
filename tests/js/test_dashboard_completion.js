"use strict";

const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");

const repoRoot = path.resolve(__dirname, "../..");
const bundle = fs.readFileSync(path.join(repoRoot, "dashboard/dist/index.js"), "utf8");

async function completeTask(resultText, confirmed, largeFixture = false, initialTask = null) {
  const requests = [];
  const prompts = ["npm test", resultText];
  const promptCalls = [];
  const confirmCalls = [];
  let page;
  const Button = function Button() {};
  const components = {
    Badge: function Badge() {},
    Button,
    Card: function Card() {},
    CardContent: function CardContent() {},
    CardHeader: function CardHeader() {},
    CardTitle: function CardTitle() {},
    Input: function Input() {},
    Label: function Label() {},
    Separator: function Separator() {},
  };
  const task = initialTask || {
    id: "M001-T001",
    title: "Verify behavior",
    objective: "Run the focused test",
    status: "in_progress",
    risk: "low",
  };
  const tasks = Array.from({ length: 20 }, (_, index) => ({
    ...task,
    id: initialTask ? task.id : `M001-T${String(index + 1).padStart(3, "0")}`,
    title: initialTask ? task.title : `Task ${index + 1}`,
  }));
  const snapshot = {
    project: { name: "Fixture", mode: "quick" },
    state: { status: "executing", active_milestone: "M001" },
    task_counts: { in_progress: 20 },
    active_tasks: tasks.slice(0, 12),
    active_task_count: tasks.length,
    active_tasks_truncated: true,
    next: { wave: tasks.slice(0, 4) },
    roadmap: [],
    requirements: [],
  };
  const states = [[], "/tmp/sdd-fixture", "", "", "auto", snapshot, null, [], null, "", false];
  let stateIndex = 0;
  const SDK = {
    React: {
      Fragment: Symbol("Fragment"),
      createElement(type, props, ...children) {
        return { type, props: props || {}, children: children.flat(Infinity) };
      },
    },
    hooks: {
      useState(initial) {
        const current = stateIndex++;
        return [states[current] === undefined ? initial : states[current], () => {}];
      },
      useEffect() {},
      useMemo(callback) { return callback(); },
    },
    components,
    fetchJSON(url, options) {
      let body = options && options.body;
      if (typeof body === "string") body = JSON.parse(body);
      requests.push({ url, method: options && options.method, body });
      if (url.endsWith("/sources")) return Promise.resolve({ sources: [] });
      if (url.includes("/snapshot?")) return Promise.resolve(snapshot);
      if (url.includes("/events?")) return Promise.resolve({ events: [] });
      return Promise.resolve({ ok: true });
    },
  };
  const window = {
    __HERMES_PLUGIN_SDK__: SDK,
    __HERMES_PLUGINS__: { register(_name, component) { page = component; } },
    confirm(message) {
      confirmCalls.push(message);
      return confirmed;
    },
    prompt(message, defaultValue) {
      promptCalls.push({ message, defaultValue });
      return prompts.shift() ?? null;
    },
    setInterval() { return 1; },
    clearInterval() {},
  };
  const context = {
    window,
    localStorage: { getItem() { return "/tmp/sdd-fixture"; }, setItem() {} },
    navigator: { clipboard: { writeText() { return Promise.resolve(); } } },
    Promise,
    Object,
    String,
    encodeURIComponent,
    console,
  };
  vm.runInNewContext(bundle, context, { filename: "dashboard/dist/index.js" });
  assert.equal(typeof page, "function");
  const tree = page();
  function visit(node) {
    if (Array.isArray(node)) return node.flatMap(visit);
    if (!node || typeof node !== "object") return [];
    return [node, ...visit(node.children)];
  }
  if (largeFixture) {
    assert.equal(snapshot.active_tasks.length, 12);
    assert.equal(snapshot.active_task_count, 20);
    assert.equal(snapshot.active_tasks_truncated, true);
    return { evidence: null, promptCalls, confirmCalls };
  }
  const actionButton = visit(tree).find(
    (node) => node.type === Button && node.children.includes(task.status === "done" ? "Record verification" : "Implementation complete"),
  );
  assert.ok(actionButton, "task exposes the appropriate implementation or verification action");
  actionButton.props.onClick();
  await new Promise((resolve) => setTimeout(resolve, 0));
  const operation = requests.find((request) => request.body && request.body.operation === "transition");
  assert.ok(operation, "completion issues a transition operation");
  return { evidence: operation.body.payload.evidence, promptCalls, confirmCalls, requests, operation, task };
}

(async () => {
  const largeSnapshot = await completeTask("passed", true, true);
  assert.equal(largeSnapshot.evidence, null, "large-project fixture retains a bounded task preview");

  const negative = await completeTask("not verified", false, false, {
    id: "M001-T001",
    title: "Verify behavior",
    objective: "Run the focused test",
    status: "in_progress",
    risk: "low",
  });
  assert.equal(negative.evidence.passed, false, "a negative result cannot be heuristically marked passed");
  assert.equal(negative.promptCalls[1].defaultValue, "", "the result prompt must not default to success");
  assert.equal(negative.confirmCalls.length, 1);
  assert.match(negative.confirmCalls[0], /actually run|verification/i);

  const positive = await completeTask("passed", true, false, {
    id: "M001-T001",
    title: "Verify behavior",
    objective: "Run the focused test",
    status: "in_progress",
    risk: "low",
  });
  assert.equal(positive.evidence.passed, true, "success requires an explicit confirmation");
  assert.equal(positive.confirmCalls.length, 1);

  const alreadyDone = await completeTask("passed", true, false, {
    id: "M001-T002",
    title: "Previously completed",
    objective: "Verify later",
    status: "done",
    risk: "low",
    evidence_ids: [],
  });
  assert.equal(alreadyDone.evidence.passed, true, "verification can be recorded after implementation is marked done");
  assert.equal(alreadyDone.operation.body.target, alreadyDone.task.id);
  console.log("Dashboard completion evidence tests passed");
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
