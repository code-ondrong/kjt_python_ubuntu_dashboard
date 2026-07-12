#!/usr/bin/env python3
"""
Remote server helper — run commands, deploy, or snapshot the dashboard host
over SSH using the credentials in the project ``.env``:

    SERVER_SSH=<host or host:port>   # e.g. 192.168.100.25 or 192.168.100.25:22
    ROOT_USER=<ssh user>            # e.g. code
    ROOT_PASSWORD=<ssh/sudo password>

Usage:
    python scripts/remote.py status                       # read-only health snapshot
    python scripts/remote.py run "uptime"                 # run a command
    python scripts/remote.py run --sudo "systemctl restart dashboard"
    python scripts/remote.py deploy                       # upload code + restart service

Notes:
  * Credentials are read from .env and are never printed.
  * `--sudo` feeds the password to `sudo -S` over stdin (user `code`'s password).
  * Requires: pip install paramiko
"""

import argparse
import os
import posixpath
import sys

try:
    import paramiko
except ImportError:
    sys.exit("paramiko is not installed — run: pip install paramiko")


PROJECT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STAGE_DIR = "~/.dashboard_deploy"          # staging dir in the SSH user's home
INSTALL_DIR = "/opt/system-monitor"
SERVICE_DST = "/etc/systemd/system/dashboard.service"

# Files copied into INSTALL_DIR on deploy.
PY_FILES = [
    "main.py", "config.py", "system_stats.py", "gpu_stats.py",
    "dashboard.py", "docker_stats.py", "cloudflared_stats.py",
    "process_manager.py",
]
SERVICE_FILE = os.path.join("systemd", "dashboard.service")


# ── .env ─────────────────────────────────────────────────────────────────

def load_env() -> dict:
    path = os.path.join(PROJECT_DIR, ".env")
    if not os.path.isfile(path):
        sys.exit(f".env not found at {path}")
    env = {}
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, val = line.split("=", 1)
            env[key.strip()] = val.strip().strip('"').strip("'")
    for required in ("SERVER_SSH", "ROOT_USER", "ROOT_PASSWORD"):
        if not env.get(required):
            sys.exit(f".env is missing {required}")
    return env


# ── SSH ──────────────────────────────────────────────────────────────────

def connect(env: dict) -> paramiko.SSHClient:
    host = env["SERVER_SSH"]
    port = 22
    if ":" in host:
        host, port_str = host.rsplit(":", 1)
        port = int(port_str)
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    client.connect(
        hostname=host, port=port,
        username=env["ROOT_USER"], password=env["ROOT_PASSWORD"],
        timeout=12, look_for_keys=False, allow_agent=False,
    )
    return client


def run_cmd(client, env, cmd, sudo=False, timeout=120):
    """Run *cmd* on the server; return (exit_code, stdout, stderr)."""
    if sudo:
        cmd = "sudo -S -p '' " + cmd
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    if sudo:
        stdin.write(env["ROOT_PASSWORD"] + "\n")
        stdin.flush()
    out = stdout.read().decode("utf-8", "replace")
    err = stderr.read().decode("utf-8", "replace")
    code = stdout.channel.recv_exit_status()
    return code, out, err


def _echo(code, out, err):
    if out.strip():
        print(out.rstrip())
    if err.strip():
        print("[stderr]", err.rstrip())
    return code


# ── Commands ─────────────────────────────────────────────────────────────

def cmd_run(client, env, args):
    code, out, err = run_cmd(client, env, args.command, sudo=args.sudo)
    _echo(code, out, err)
    return code


def cmd_status(client, env, _args):
    checks = [
        ("hostname / uptime",       "hostname; uptime", False),
        ("dashboard service",       "systemctl is-active dashboard; systemctl --no-pager -l -n 3 status dashboard | tail -n 4", False),
        ("cloudflared service",     "systemctl is-active cloudflared", False),
        ("cloudflared metrics port", "ss -tlnp 2>/dev/null | grep -i cloudflared || echo '(metrics port not found)'", True),
        ("installed .env keys",     "cut -d= -f1 " + INSTALL_DIR + "/.env 2>/dev/null || echo '(no .env)'", True),
        ("cloudflared_stats present", "ls -l " + INSTALL_DIR + "/cloudflared_stats.py 2>/dev/null || echo '(missing)'", False),
    ]
    for title, command, sudo in checks:
        print(f"\n=== {title} ===")
        code, out, err = run_cmd(client, env, command, sudo=sudo, timeout=30)
        _echo(code, out, err)
    return 0


def cmd_deploy(client, env, _args):
    sftp = client.open_sftp()

    # Resolve the staging dir (~ -> absolute) and (re)create it.
    home = run_cmd(client, env, "echo $HOME")[1].strip()
    stage = STAGE_DIR.replace("~", home)
    run_cmd(client, env, f"mkdir -p {stage}/systemd")

    # Upload files via SFTP.
    print(f"Uploading to {stage} ...")
    for name in PY_FILES:
        local = os.path.join(PROJECT_DIR, name)
        if not os.path.isfile(local):
            print(f"  skip (missing locally): {name}")
            continue
        sftp.put(local, posixpath.join(stage, name))
        print(f"  ✓ {name}")
    sftp.put(os.path.join(PROJECT_DIR, SERVICE_FILE),
             posixpath.join(stage, "systemd", "dashboard.service"))
    print("  ✓ systemd/dashboard.service")
    sftp.close()

    # Install into place + restart (all under sudo).
    steps = [
        f"cp {stage}/*.py {INSTALL_DIR}/",
        f"cp {stage}/systemd/dashboard.service {SERVICE_DST}",
        f"chown dashboard:dashboard {INSTALL_DIR}/*.py",
        "systemctl daemon-reload",
        "systemctl restart dashboard",
    ]
    print("Installing + restarting ...")
    for step in steps:
        code, out, err = run_cmd(client, env, step, sudo=True, timeout=60)
        status = "ok" if code == 0 else f"FAILED({code})"
        print(f"  [{status}] {step}")
        if code != 0 and err.strip():
            print("     ", err.strip())
    code, out, _ = run_cmd(client, env, "systemctl is-active dashboard")
    print("dashboard is-active:", out.strip())
    return 0


def main():
    parser = argparse.ArgumentParser(description="Remote dashboard helper (SSH via .env)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_run = sub.add_parser("run", help="run a command on the server")
    p_run.add_argument("command")
    p_run.add_argument("--sudo", action="store_true", help="run under sudo -S")

    sub.add_parser("status", help="read-only health snapshot")
    sub.add_parser("deploy", help="upload code + restart the service")

    args = parser.parse_args()
    env = load_env()
    client = connect(env)
    try:
        handler = {"run": cmd_run, "status": cmd_status, "deploy": cmd_deploy}[args.cmd]
        rc = handler(client, env, args)
    finally:
        client.close()
    sys.exit(rc)


if __name__ == "__main__":
    main()
