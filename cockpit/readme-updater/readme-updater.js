(function () {
  const $ = (id) => document.getElementById(id);

  function quote(value) {
    return "'" + String(value).replace(/'/g, "'\"'\"'") + "'";
  }

  function run(command) {
    return cockpit.spawn(["bash", "-lc", command], { superuser: "try", err: "out" });
  }

  function setText(id, text) {
    $(id).textContent = text || "";
  }

  function calendarForMode() {
    const mode = $("mode").value;
    if (mode === "hourly") return "hourly";
    if (mode === "daily") return "*-*-* 04:17:00";
    if (mode === "weekly") return "Sun *-*-* 04:17:00";
    return $("calendar").value.trim();
  }

  function refresh() {
    const command = [
      "systemctl is-enabled readme-updater.timer 2>/dev/null || true",
      "systemctl is-active readme-updater.timer 2>/dev/null || true",
      "systemctl is-active readme-updater.service 2>/dev/null || true",
      "systemctl list-timers readme-updater.timer --no-pager || true",
      "test -f /etc/readme-updater.env && echo token-file: present || echo token-file: missing",
      "git -C /srv/github/.github log -1 --oneline 2>/dev/null || true",
    ].join("; ");

    run(command)
      .then((out) => setText("status", out))
      .catch((err) => setText("status", err));

    run("journalctl -u readme-updater.service -n 120 --no-pager || true")
      .then((out) => setText("logs", out))
      .catch((err) => setText("logs", err));
  }

  $("refresh").addEventListener("click", refresh);

  $("run-now").addEventListener("click", function () {
    setText("run-output", "Starting readme-updater.service...");
    run("systemctl start readme-updater.service && systemctl status readme-updater.service --no-pager")
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
    run("git -C /srv/github/.github pull --ff-only")
      .then((out) => {
        setText("run-output", out);
        refresh();
      })
      .catch((err) => setText("run-output", err));
  });

  $("save-schedule").addEventListener("click", function () {
    const mode = $("mode").value;
    const calendar = calendarForMode();
    const body = "[Timer]\\nOnCalendar=\\nOnCalendar=" + calendar + "\\nPersistent=true\\n";
    const command = [
      "mkdir -p /etc/systemd/system/readme-updater.timer.d",
      "printf %s " + quote(body) + " > /etc/systemd/system/readme-updater.timer.d/override.conf",
      "systemctl daemon-reload",
      mode === "manual" ? "systemctl disable --now readme-updater.timer" : "systemctl enable --now readme-updater.timer",
    ].join(" && ");

    run(command)
      .then(() => refresh())
      .catch((err) => setText("status", err));
  });

  $("enable-timer").addEventListener("click", function () {
    run("systemctl enable --now readme-updater.timer")
      .then(() => refresh())
      .catch((err) => setText("status", err));
  });

  $("disable-timer").addEventListener("click", function () {
    run("systemctl disable --now readme-updater.timer")
      .then(() => refresh())
      .catch((err) => setText("status", err));
  });

  $("save-token").addEventListener("click", function () {
    const token = $("token").value.trim();
    if (!token) {
      setText("status", "Token is empty.");
      return;
    }

    const body = "REPO_SYNC_TOKEN=" + token + "\\n";
    run("printf %s " + quote(body) + " > /etc/readme-updater.env && chmod 600 /etc/readme-updater.env")
      .then(() => {
        $("token").value = "";
        refresh();
      })
      .catch((err) => setText("status", err));
  });

  refresh();
})();
