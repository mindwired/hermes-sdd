(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  const React = SDK.React;
  const h = React.createElement;
  const { useEffect, useMemo, useState } = SDK.hooks;
  const {
    Badge,
    Button,
    Card,
    CardContent,
    CardHeader,
    CardTitle,
    Input,
    Label,
    Separator,
  } = SDK.components;

  function api(path, options) {
    const init = options ? Object.assign({}, options) : undefined;
    if (init && init.body && typeof init.body !== "string") {
      init.headers = Object.assign({ "Content-Type": "application/json" }, init.headers || {});
      init.body = JSON.stringify(init.body);
    }
    return SDK.fetchJSON("/api/plugins/sdd" + path, init);
  }

  function errorText(error) {
    if (!error) return "Unknown error";
    return String(error.message || error.detail || error);
  }

  function Pill(props) {
    return h(Badge, { variant: "outline" }, props.value || "unknown");
  }

  function Stat(props) {
    return h(
      "div",
      { className: "sdd-stat" },
      h("div", { className: "sdd-muted" }, props.label),
      h("div", { className: "sdd-stat-value" }, String(props.value == null ? "—" : props.value)),
      props.detail ? h("div", { className: "sdd-muted sdd-ellipsis", title: props.detail }, props.detail) : null,
    );
  }

  function SectionTitle(props) {
    return h(
      "div",
      { className: "sdd-section-title" },
      h("div", null, h("div", { className: "sdd-title" }, props.title), props.detail ? h("div", { className: "sdd-muted" }, props.detail) : null),
      props.actions || null,
    );
  }

  function Empty(props) {
    return h("div", { className: "sdd-empty" }, props.children);
  }

  function SddPage() {
    let savedRoot = "";
    try { savedRoot = localStorage.getItem("hermes.sdd.root") || ""; } catch (_) { /* ignore */ }

    const [sources, setSources] = useState([]);
    const [root, setRoot] = useState(savedRoot);
    const [newRoot, setNewRoot] = useState("");
    const [goal, setGoal] = useState("");
    const [mode, setMode] = useState("auto");
    const [snapshot, setSnapshot] = useState(null);
    const [validation, setValidation] = useState(null);
    const [events, setEvents] = useState([]);
    const [context, setContext] = useState(null);
    const [error, setError] = useState("");
    const [busy, setBusy] = useState(false);

    function sourceForCurrentRoot() {
      return sources.find(function (source) { return source.path === root; }) || null;
    }

    function loadSources() {
      return api("/sources").then(function (data) {
        const items = data.sources || [];
        setSources(items);
        if (!root && items[0]) setRoot(items[0].path);
        return items;
      });
    }

    function loadEvents(chosen) {
      const current = chosen || root;
      if (!current) { setEvents([]); return Promise.resolve(); }
      return api("/events?root=" + encodeURIComponent(current) + "&limit=20")
        .then(function (data) { setEvents(data.events || []); })
        .catch(function () { setEvents([]); });
    }

    function loadSnapshot(chosen, quiet) {
      const current = chosen || root;
      if (!current) { setSnapshot(null); setValidation(null); setEvents([]); return Promise.resolve(); }
      if (!quiet) setBusy(true);
      setError("");
      return api("/snapshot?root=" + encodeURIComponent(current))
        .then(function (data) { setSnapshot(data); return loadEvents(current).then(function () { return data; }); })
        .catch(function (failure) {
          setSnapshot(null);
          setValidation(null);
          setEvents([]);
          setError(errorText(failure));
          throw failure;
        })
        .finally(function () { if (!quiet) setBusy(false); });
    }

    function operation(name, target, payload, options) {
      setBusy(true);
      setError("");
      return api("/operation", {
        method: "POST",
        body: {
          operation: name,
          root: root,
          target: target || null,
          payload: payload || {},
          options: options || {},
        },
      })
        .then(function (result) {
          return loadSources()
            .then(function () { return loadSnapshot(root, true).catch(function () { return null; }); })
            .then(function () { return result; });
        })
        .catch(function (failure) {
          setError(errorText(failure));
          throw failure;
        })
        .finally(function () { setBusy(false); });
    }

    function addSource() {
      const requested = newRoot.trim();
      if (!requested) return;
      setBusy(true);
      setError("");
      api("/sources", { method: "POST", body: { path: requested } })
        .then(function (data) {
          const selected = data.source.path;
          setRoot(selected);
          setNewRoot("");
          return loadSources().then(function () { return loadSnapshot(selected, true).catch(function () { return null; }); });
        })
        .catch(function (failure) { setError(errorText(failure)); })
        .finally(function () { setBusy(false); });
    }

    function removeSource() {
      const source = sourceForCurrentRoot();
      if (!source || !window.confirm("Remove this repository from the SDD Dashboard source list? Project files will not be deleted.")) return;
      setBusy(true);
      api("/sources/" + encodeURIComponent(String(source.id)), { method: "DELETE" })
        .then(function () {
          setRoot("");
          setSnapshot(null);
          return loadSources();
        })
        .catch(function (failure) { setError(errorText(failure)); })
        .finally(function () { setBusy(false); });
    }

    function initialize() {
      return operation("init", null, {
        goal: goal.trim(),
        mode: mode,
        name: root.split(/[\\/]/).pop(),
      });
    }

    function validateProject() {
      setBusy(true);
      setError("");
      return api("/operation", {
        method: "POST",
        body: {
          operation: "validate",
          root: root,
          target: null,
          payload: { record: false },
          options: { detail: "normal" },
        },
      })
        .then(function (result) { setValidation(result); return result; })
        .catch(function (failure) { setError(errorText(failure)); throw failure; })
        .finally(function () { setBusy(false); });
    }

    function showContext(taskId) {
      setBusy(true);
      api("/context?root=" + encodeURIComponent(root) + (taskId ? "&task_id=" + encodeURIComponent(taskId) : ""))
        .then(function (data) { setContext(data); })
        .catch(function (failure) { setError(errorText(failure)); })
        .finally(function () { setBusy(false); });
    }

    function copyContext() {
      const text = context && context.text;
      if (!text) return;
      navigator.clipboard.writeText(text)
        .then(function () { setError(""); })
        .catch(function (failure) { setError("Could not copy context: " + errorText(failure)); });
    }

    function startTask(task) {
      return operation("transition", task.id, { status: "in_progress" });
    }

    function blockTask(task) {
      const reason = window.prompt("Why is this task blocked?", task.blocked_reason || "");
      if (!reason) return;
      return operation("transition", task.id, { status: "blocked", blocked_reason: reason });
    }

    function completeTask(task) {
      const command = window.prompt("Verification command or evidence artifact:", "");
      const result = window.prompt(
        "Verification result:",
        "",
      );
      if (!command && !result) return;
      if (!window.confirm("Did you actually run or observe this verification successfully? Choose Cancel to record the task as done with verification still pending.")) {
        return operation("transition", task.id, {
          status: "done",
          summary: "Implementation complete; verification pending",
          evidence: {
            type: "manual_or_test",
            command: command || "",
            result: result || "verification pending",
            passed: false,
          },
        });
      }
      return operation("transition", task.id, {
        status: "done",
        summary: "Completed from the Hermes SDD Dashboard",
        evidence: {
          type: "manual_or_test",
          command: command || "",
          result: result || "",
          passed: true,
        },
      });
    }

    function taskRow(task, suggested) {
      const actions = [
        h(Button, { key: "context", variant: "outline", onClick: function () { showContext(task.id); } }, "Context"),
      ];
      if (task.status === "pending" && suggested) {
        actions.push(h(Button, { key: "start", onClick: function () { startTask(task); }, disabled: busy }, "Start"));
      }
      if (task.status === "in_progress") {
        actions.push(h(Button, { key: "block", variant: "outline", onClick: function () { blockTask(task); }, disabled: busy }, "Block"));
        actions.push(h(Button, { key: "done", onClick: function () { completeTask(task); }, disabled: busy }, "Implementation complete"));
      }
      if (task.status === "done" && (!task.evidence_ids || task.evidence_ids.length === 0)) {
        actions.push(h(Button, { key: "verify", variant: "outline", onClick: function () { completeTask(task); }, disabled: busy }, "Record verification"));
      }
      if (task.status === "blocked") {
        actions.push(h(Button, { key: "resume", onClick: function () { operation("transition", task.id, { status: "pending", blocked_reason: "" }); }, disabled: busy }, "Return to pending"));
      }
      return h(
        "div",
        { className: "sdd-row", key: task.id },
        h(
          "div",
          { className: "sdd-row-main" },
          h("div", { className: "sdd-title" }, task.id + " — " + task.title),
          h("div", { className: "sdd-muted" }, task.objective || "No objective recorded."),
          task.depends_on && task.depends_on.length ? h("div", { className: "sdd-muted" }, "Depends on: " + task.depends_on.join(", ")) : null,
          task.blocked_reason ? h("div", { className: "sdd-warning" }, task.blocked_reason) : null,
        ),
        h(
          "div",
          { className: "sdd-actions" },
          h(Pill, { value: task.status }),
          h(Pill, { value: task.risk }),
          actions,
        ),
      );
    }

    useEffect(function () {
      loadSources().catch(function (failure) { setError(errorText(failure)); });
    }, []);

    useEffect(function () {
      if (!root) return undefined;
      try { localStorage.setItem("hermes.sdd.root", root); } catch (_) { /* ignore */ }
      loadSnapshot(root).catch(function () { /* visible error already set */ });
      const timer = window.setInterval(function () {
        loadSnapshot(root, true).catch(function () { /* keep prior state during transient errors */ });
      }, 15000);
      return function () { window.clearInterval(timer); };
    }, [root]);

    const activeTasks = (snapshot && snapshot.active_tasks) || [];
    const nextWave = (snapshot && snapshot.next && snapshot.next.wave) || [];
    const counts = (snapshot && snapshot.task_counts) || {};
    const taskTotal = useMemo(function () {
      return Object.values(counts).reduce(function (sum, value) { return sum + Number(value || 0); }, 0);
    }, [counts]);

    const source = sourceForCurrentRoot();
    const findings = (validation && validation.findings) || [];

    return h(
      "div",
      { className: "sdd-page" },
      h(
        Card,
        null,
        h(CardHeader, null, h(CardTitle, null, "Spec-driven development")),
        h(
          CardContent,
          null,
          h(
            "div",
            { className: "sdd-toolbar" },
            h(
              "div",
              { className: "sdd-field sdd-field-wide" },
              h(Label, null, "Project"),
              h(
                "select",
                { className: "sdd-select", value: root, onChange: function (event) { setRoot(event.target.value); } },
                h("option", { value: "" }, "Select a source"),
                sources.map(function (item) {
                  const suffix = item.exists ? (item.initialized ? "" : " · not initialized") : " · missing";
                  return h("option", { key: item.id, value: item.path }, item.name + suffix + " — " + item.path);
                }),
              ),
            ),
            h("div", { className: "sdd-field sdd-field-wide" }, h(Label, null, "Register local repository"), h(Input, { value: newRoot, placeholder: "/path/to/repository", onChange: function (event) { setNewRoot(event.target.value); } })),
            h(Button, { onClick: addSource, disabled: busy || !newRoot.trim() }, "Add"),
            h(Button, { onClick: function () { loadSnapshot(root); }, disabled: busy || !root }, busy ? "Working…" : "Refresh"),
            source ? h(Button, { variant: "outline", onClick: removeSource, disabled: busy }, "Remove source") : null,
          ),
          error ? h("div", { className: "sdd-alert sdd-alert-error" }, error) : null,
        ),
      ),

      root && !snapshot ? h(
        Card,
        null,
        h(CardHeader, null, h(CardTitle, null, "Initialize this repository")),
        h(
          CardContent,
          null,
          h("p", { className: "sdd-muted" }, "The repository is registered but no .sdd/project.json was found."),
          h(
            "div",
            { className: "sdd-toolbar" },
            h("div", { className: "sdd-field sdd-field-grow" }, h(Label, null, "Project goal"), h(Input, { value: goal, placeholder: "The outcome this project must deliver", onChange: function (event) { setGoal(event.target.value); } })),
            h(
              "div",
              { className: "sdd-field" },
              h(Label, null, "Rigor"),
              h("select", { className: "sdd-select", value: mode, onChange: function (event) { setMode(event.target.value); } }, ["auto", "quick", "standard", "deep", "program"].map(function (value) { return h("option", { key: value, value: value }, value); })),
            ),
            h(Button, { onClick: initialize, disabled: busy || !goal.trim() }, "Initialize .sdd"),
          ),
        ),
      ) : null,

      snapshot ? h(
        React.Fragment,
        null,
        h(
          "div",
          { className: "sdd-grid" },
          h(Stat, { label: "Health", value: snapshot.health && snapshot.health.score, detail: JSON.stringify((snapshot.health && snapshot.health.counts) || {}) }),
          h(Stat, { label: "Mode", value: snapshot.project && snapshot.project.mode, detail: snapshot.state && snapshot.state.status }),
          h(Stat, { label: "Milestones", value: snapshot.milestone_count, detail: snapshot.state && snapshot.state.active_milestone }),
          h(Stat, { label: "Tasks", value: taskTotal, detail: JSON.stringify(counts) }),
        ),

        snapshot.action ? h(
          Card,
          null,
          h(CardContent, { className: "sdd-card-content" },
            h(SectionTitle, {
              title: "Recommended next action",
              detail: snapshot.action.reason,
            }),
            h("div", { className: "sdd-muted" }, "Action: " + snapshot.action.kind),
            snapshot.active_validation && snapshot.active_validation.error_count
              ? h("div", { className: "sdd-list" }, snapshot.active_validation.findings.map(function (finding, index) {
                return h("div", { className: "sdd-finding sdd-finding-error", key: finding.code + "-" + index },
                  h("div", { className: "sdd-title" }, finding.code),
                  h("div", null, finding.message),
                  finding.target ? h("div", { className: "sdd-muted" }, finding.target) : null,
                );
              }))
              : null,
            snapshot.active_task_count > ((snapshot.active_tasks || []).length)
              ? h("div", { className: "sdd-muted" },
                "Showing " + (snapshot.active_tasks || []).length + " of " + snapshot.active_task_count + " active-milestone tasks. Use the task list and next safe wave for focused context.",
              )
              : null,
          ),
        ) : null,

        h(
          Card,
          null,
          h(CardContent, { className: "sdd-card-content" }, h(SectionTitle, {
            title: "Next safe wave",
            detail: "Dependency-ready work that can start without overlapping active scopes.",
            actions: h(Button, { variant: "outline", onClick: validateProject, disabled: busy }, "Validate project"),
          }), nextWave.length ? h("div", { className: "sdd-list" }, nextWave.map(function (task) { return taskRow(task, true); })) : h(Empty, null, "No dependency-ready task is currently available.")),
        ),

        h(
          Card,
          null,
          h(CardContent, { className: "sdd-card-content" }, h(SectionTitle, { title: "Active milestone tasks", detail: snapshot.state && snapshot.state.active_milestone ? snapshot.state.active_milestone : "No active milestone" }), activeTasks.length ? h("div", { className: "sdd-list" }, activeTasks.map(function (task) { return taskRow(task, false); })) : h(Empty, null, "The active milestone has no plan yet.")),
        ),

        h(
          "div",
          { className: "sdd-two-column" },
          h(
            Card,
            null,
            h(CardContent, { className: "sdd-card-content" }, h(SectionTitle, { title: "Roadmap", detail: "Outcome-oriented milestones" }), (snapshot.roadmap || []).length ? h("div", { className: "sdd-list" }, (snapshot.roadmap || []).map(function (milestone) {
              return h("div", { className: "sdd-row sdd-row-compact", key: milestone.id }, h("div", { className: "sdd-row-main" }, h("div", { className: "sdd-title" }, milestone.id + " — " + milestone.title), h("div", { className: "sdd-muted" }, milestone.objective || "No objective recorded.")), h(Pill, { value: milestone.status }));
            })) : h(Empty, null, "No milestones recorded.")),
          ),
          h(
            Card,
            null,
            h(CardContent, { className: "sdd-card-content" }, h(SectionTitle, { title: "Requirements", detail: "Behavioral contracts linked to milestones" }), (snapshot.requirements || []).length ? h("div", { className: "sdd-list" }, (snapshot.requirements || []).slice(0, 12).map(function (requirement) {
              return h("div", { className: "sdd-row sdd-row-compact", key: requirement.id }, h("div", { className: "sdd-row-main" }, h("div", { className: "sdd-title" }, requirement.id + " — " + requirement.title), h("div", { className: "sdd-muted" }, requirement.statement || "")), h(Pill, { value: requirement.priority }));
            })) : h(Empty, null, "No requirements recorded.")),
          ),
        ),

        validation ? h(
          Card,
          null,
          h(CardContent, { className: "sdd-card-content" }, h(SectionTitle, { title: "Validation", detail: "Health " + validation.score + " · " + JSON.stringify(validation.counts || {}) }), findings.length ? h("div", { className: "sdd-list" }, findings.map(function (finding, index) {
            return h("div", { className: "sdd-finding sdd-finding-" + finding.severity, key: finding.code + "-" + index }, h("div", { className: "sdd-title" }, finding.code), h("div", null, finding.message), finding.target ? h("div", { className: "sdd-muted" }, finding.target) : null);
          })) : h(Empty, null, "No validation findings.")),
        ) : null,

        h(
          Card,
          null,
          h(CardContent, { className: "sdd-card-content" }, h(SectionTitle, { title: "Recent lifecycle events", detail: "Compact recovery and audit trail" }), events.length ? h("div", { className: "sdd-events" }, events.slice().reverse().map(function (event, index) {
            return h("div", { className: "sdd-event", key: String(event.at || index) + index }, h("span", { className: "sdd-event-time" }, event.at || ""), h("span", { className: "sdd-title" }, event.kind || "event"), h("code", { className: "sdd-event-data" }, JSON.stringify(event)));
          })) : h(Empty, null, "No events recorded.")),
        ),

        context ? h(
          Card,
          null,
          h(CardContent, { className: "sdd-card-content" }, h(SectionTitle, {
            title: "Bounded context pack",
            detail: (context.estimated_tokens || "—") + " estimated tokens",
            actions: h("div", { className: "sdd-actions" }, h(Button, { variant: "outline", onClick: copyContext }, "Copy"), h(Button, { variant: "outline", onClick: function () { setContext(null); } }, "Close")),
          }), Separator ? h(Separator, null) : null, h("pre", { className: "sdd-pre" }, context.text || JSON.stringify(context, null, 2))),
        ) : null,
      ) : null,
    );
  }

  window.__HERMES_PLUGINS__.register("sdd", SddPage);
})();
