(function () {
  const $ = (id) => document.getElementById(id);
  const configPath = "/etc/github-actions-cockpit/actions.json";

  const defaultActions = [
    {
      id: "readme-updater",
      title: "README updater",
      description: "Обновляет README.md, README.en.md, traffic-views.png и resources/header.svg во всех репозиториях.",
      service: "readme-updater.service",
      timer: "readme-updater.timer",
      defaultCalendar: "*-*-* 04:17:00"
    },
    {
      id: "license-sync",
      title: "LICENSE sync",
      description: "Синхронизирует LICENSE.md из .github во все репозитории.",
      service: "license-sync.service",
      timer: "license-sync.timer",
      defaultCalendar: "Sun *-*-* 04:47:00"
    },
    {
      id: "github-actions-updater",
      title: "GitHub Actions updater",
      description: "Обновляет локальную копию .github, Cockpit-панель, systemd units и список actions.",
      service: "github-actions-updater.service",
      timer: "github-actions-updater.timer",
      defaultCalendar: "*-*-* 03:47:00"
    }
  ];

  let actions = defaultActions.slice();
  let selectedAction = actions[0];

  function quote(value) {
    return "'" + String(value).replace(/'/g, "'\"'\"'") + "'";
  }

  function run(command) {
    return cockpit.spawn(["bash", "-lc", command], { superuser: "try", err: "out" });
  }

  function setText(id, text) {
    $(id).textContent = text || "";
  }

  function currentAction() {
    return actions.find((action) => action.id === $("action-select").value) || actions[0];
  }

  function calendarForMode() {
    const action = currentAction();
    const mode = $("mode").value;
    if (mode === "hourly") return "hourly";
    if (mode === "daily") return "*-*-* 04:17:00";
    if (mode === "weekly") return "Sun *-*-* 04:17:00";
    if (mode === "manual") return action.defaultCalendar || "*-*-* 04:17:00";
    return $("calendar").value.trim();
  }

  function modeForCalendar(enabled, calendar, action) {
    if (enabled !== "enabled") return "manual";
    if (calendar === "hourly") return "hourly";
    if (calendar === "*-*-* 04:17:00") return "daily";
    if (calendar === "Sun *-*-* 04:17:00") return "weekly";
    if (calendar === (action.defaultCalendar || "")) return "custom";
    return "custom";
  }

  function renderActions() {
    $("action-select").innerHTML = "";
    actions.forEach((action) => {
      const option = document.createElement("option");
      option.value = action.id;
      option.textContent = action.title || action.id;
      $("action-select").appendChild(option);
    });
    $("actions-config").value = JSON.stringify(actions, null, 2);
    updateSelectedAction();
  }

  function updateSelectedAction() {
    selectedAction = currentAction();
    $("action-description").textContent = selectedAction.description || "";
    $("calendar").value = selectedAction.defaultCalendar || "*-*-* 04:17:00";
    syncScheduleForm(selectedAction);
    refresh();
  }

  function syncScheduleForm(action) {
    const command = [
      "if systemctl is-enabled --quiet " + quote(action.timer) + " 2>/dev/null; then enabled=enabled; else enabled=disabled; fi",
      "calendar=$(systemctl cat " + quote(action.timer) + " 2>/dev/null | awk -F= '/^OnCalendar=/{value=$2} END{print value}')",
      "printf 'enabled=%s\\ncalendar=%s\\n' \"$enabled\" \"$calendar\""
    ].join("; ");

    run(command)
      .then((out) => {
        const data = {};
        out.split(/\r?\n/).forEach((line) => {
          const index = line.indexOf("=");
          if (index > -1) data[line.slice(0, index)] = line.slice(index + 1);
        });
        const calendar = data.calendar || action.defaultCalendar || "*-*-* 04:17:00";
        $("calendar").value = calendar;
        $("mode").value = modeForCalendar(data.enabled || "", calendar, action);
      })
      .catch(() => {
        $("calendar").value = action.defaultCalendar || "*-*-* 04:17:00";
        $("mode").value = "custom";
      });
  }

  function serviceCommands(action) {
    return [
      "echo action: " + quote(action.title || action.id),
      "echo service: " + quote(action.service),
      "echo timer: " + quote(action.timer),
      "printf 'timer-enabled='; systemctl is-enabled " + quote(action.timer) + " 2>/dev/null || true",
      "printf 'timer-active='; systemctl is-active " + quote(action.timer) + " 2>/dev/null || true",
      "printf 'service-active='; systemctl is-active " + quote(action.service) + " 2>/dev/null || true",
      "systemctl list-timers " + quote(action.timer) + " --no-pager || true",
      "test -f /etc/readme-updater.env && echo token-file: present || echo token-file: missing",
      "git -C /srv/github/.github log -1 --oneline 2>/dev/null || true"
    ].join("; ");
  }

  function refresh() {
    const action = currentAction();
    run(serviceCommands(action))
      .then((out) => setText("status", out))
      .catch((err) => setText("status", err));

    run("journalctl -u " + quote(action.service) + " -n 160 --no-pager || true")
      .then((out) => setText("logs", out))
      .catch((err) => setText("logs", err));
  }

  function loadConfig() {
    run("cat " + quote(configPath) + " 2>/dev/null || true")
      .then((out) => {
        if (!out.trim()) {
          actions = defaultActions.slice();
        } else {
          actions = JSON.parse(out);
        }
        renderActions();
      })
      .catch((err) => {
        setText("status", err);
        actions = defaultActions.slice();
        renderActions();
      });
  }

  $("action-select").addEventListener("change", updateSelectedAction);
  $("refresh").addEventListener("click", refresh);
  $("load-config").addEventListener("click", loadConfig);

  $("save-config").addEventListener("click", function () {
    let parsed;
    try {
      parsed = JSON.parse($("actions-config").value);
      if (!Array.isArray(parsed)) throw new Error("Config must be a JSON array.");
    } catch (error) {
      setText("status", "Ошибка JSON: " + error.message);
      return;
    }

    const body = JSON.stringify(parsed, null, 2) + "\n";
    const command = [
      "mkdir -p /etc/github-actions-cockpit",
      "printf %s " + quote(body) + " > " + quote(configPath),
      "chmod 644 " + quote(configPath)
    ].join(" && ");

    run(command)
      .then(() => {
        actions = parsed;
        renderActions();
      })
      .catch((err) => setText("status", err));
  });

  $("run-now").addEventListener("click", function () {
    const action = currentAction();
    setText("run-output", "Запуск " + action.service + "...");
    run("systemctl start " + quote(action.service) + " && systemctl status " + quote(action.service) + " --no-pager")
      .then((out) => {
        setText("run-output", out);
        refresh();
      })
      .catch((err) => {
        setText("run-output", err);
        refresh();
      });
  });

  $("pull-scripts").addEventListener("click", function () {
    run("git -C /srv/github/.github pull --ff-only && bash /srv/github/.github/scripts/install-github-actions-cockpit.sh")
      .then((out) => {
        setText("run-output", out);
        refresh();
      })
      .catch((err) => setText("run-output", err));
  });

  $("save-schedule").addEventListener("click", function () {
    const action = currentAction();
    const mode = $("mode").value;
    const calendar = calendarForMode();
    const body = "[Timer]\\nOnCalendar=\\nOnCalendar=" + calendar + "\\nPersistent=true\\n";
    const override = "/etc/systemd/system/" + action.timer + ".d/override.conf";
    const command = [
      "mkdir -p " + quote("/etc/systemd/system/" + action.timer + ".d"),
      "printf %s " + quote(body) + " > " + quote(override),
      "systemctl daemon-reload",
      mode === "manual" ? "systemctl disable --now " + quote(action.timer) : "systemctl enable --now " + quote(action.timer)
    ].join(" && ");

    run(command)
      .then(() => {
        syncScheduleForm(action);
        refresh();
      })
      .catch((err) => setText("status", err));
  });

  $("enable-timer").addEventListener("click", function () {
    const action = currentAction();
    run("systemctl enable --now " + quote(action.timer))
      .then(() => {
        syncScheduleForm(action);
        refresh();
      })
      .catch((err) => setText("status", err));
  });

  $("disable-timer").addEventListener("click", function () {
    const action = currentAction();
    run("systemctl disable --now " + quote(action.timer))
      .then(() => {
        syncScheduleForm(action);
        refresh();
      })
      .catch((err) => setText("status", err));
  });

  $("save-token").addEventListener("click", function () {
    const token = $("token").value.trim();
    if (!token) {
      setText("status", "Токен пустой.");
      return;
    }
    if (!/^github_pat_[A-Za-z0-9_]+$/.test(token)) {
      setText("status", "Токен должен начинаться с github_pat_ и содержать только латинские буквы, цифры и подчёркивания.");
      return;
    }

    const command = [
      "TOKEN_VALUE=" + quote(token) + " python3 - <<'PY'",
      "from pathlib import Path",
      "import json",
      "import os",
      "import re",
      "import tempfile",
      "import urllib.error",
      "import urllib.request",
      "",
      "token = os.environ.get('TOKEN_VALUE', '').strip()",
      "if not re.fullmatch(r'github_pat_[A-Za-z0-9_]+', token):",
      "    raise SystemExit('Invalid token format.')",
      "",
      "request = urllib.request.Request(",
      "    'https://api.github.com/user',",
      "    headers={",
      "        'Authorization': 'Bearer ' + token,",
      "        'Accept': 'application/vnd.github+json',",
      "        'X-GitHub-Api-Version': '2022-11-28',",
      "        'User-Agent': 'github-actions-cockpit'",
      "    },",
      ")",
      "try:",
      "    with urllib.request.urlopen(request, timeout=20) as response:",
      "        data = json.loads(response.read().decode('utf-8'))",
      "except urllib.error.HTTPError as error:",
      "    body = error.read().decode('utf-8', errors='replace')",
      "    raise SystemExit(f'GitHub rejected token: HTTP {error.code}: {body}')",
      "",
      "with tempfile.NamedTemporaryFile('w', encoding='utf-8', dir='/etc', delete=False) as handle:",
      "    handle.write('REPO_SYNC_TOKEN=' + token + '\\n')",
      "    tmp = handle.name",
      "os.chmod(tmp, 0o600)",
      "Path(tmp).replace('/etc/readme-updater.env')",
      "print('Token saved for GitHub user: ' + data.get('login', 'unknown'))",
      "PY"
    ].join("\n");

    run(command)
      .then((out) => {
        $("token").value = "";
        setText("status", out);
        setText("run-output", out);
        refresh();
      })
      .catch((err) => setText("status", err));
  });

  loadConfig();
})();
