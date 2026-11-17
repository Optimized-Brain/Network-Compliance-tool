# Network Switch Compliance Checker

A one-click web-based tool to audit network switch configurations against a golden hardening template. Pulls running configs from all switches pan-India via SSH, compares against 70+ compliance rules, and generates a comprehensive dashboard with downloadable PDF and CSV reports.

![Dashboard](docs/screenshot.png)

---

## Features

- **One-Click Audit** — Single button to SSH into all switches, pull configs, and run compliance checks
- **Golden Template** — 70+ rules covering 13 security categories (AAA, SSH, NAC, SNMP, hardening, etc.)
- **Live Dashboard** — Real-time progress tracking, compliance gauges, severity breakdowns, region-wise stats
- **Detailed Reports** — Per-switch drill-down showing every compliant/non-compliant rule with remediation
- **Downloadable Reports** — PDF (formatted) and CSV (summary + detailed) for offline analysis
- **Multi-vendor Support** — Cisco IOS/NX-OS/XE, Arista, Juniper, HP, Huawei via Netmiko
- **Bastion/Jump Host** — Built-in support for SSH through a jump host (your RDP bastion server)
- **Demo Mode** — Test the tool with simulated data before connecting to real switches
- **Parallel Collection** — Concurrent SSH sessions (configurable) for fast audits

---

## Quick Start

### 1. Prerequisites
- Python 3.9+
- Network access to switches from the bastion server (SSH port 22)

### 2. Install & Run (Demo Mode)

```bash
# Clone/copy the project to your bastion server
cd network-compliance-checker

# Option A: Use the launcher script (Windows)
run.bat

# Option B: Manual setup
python -m venv venv
venv\Scripts\activate      # Windows
# source venv/bin/activate # Linux
pip install -r requirements.txt
python app.py
```

Open **http://localhost:5000** in your browser and click **"Run Compliance Audit"**.

### 3. Switch to Live Mode

```bash
# Set environment variable before running
set COMPLIANCE_MODE=live    # Windows
# export COMPLIANCE_MODE=live  # Linux

python app.py

# Or use the launcher
run.bat live
```

---

## Configuration

### Switch Inventory (`config/inventory.yaml`)

Add all your switches organized by region:

```yaml
global_defaults:
  device_type: cisco_ios
  username: admin
  password: "your_password"
  secret: "enable_secret"
  port: 22
  timeout: 30
  # Uncomment for bastion/jump host SSH tunneling:
  # jump_host:
  #   hostname: 10.0.0.1
  #   username: bastion_user
  #   password: "bastion_pass"

regions:
  - region: "North Zone"
    location: "Delhi"
    switches:
      - name: "DELHI-CORE-SW01"
        hostname: "10.1.1.1"
        device_type: cisco_ios
      - name: "DELHI-DIST-SW01"
        hostname: "10.1.1.2"
```

### Golden Template (`config/golden_template.yaml`)

The template includes 70+ rules across 13 categories:

| Category | Rules | Covers |
|----------|-------|--------|
| AAA & Authentication | 9 | TACACS+, local fallback, login/enable/exec auth |
| SSH Hardening | 5 | SSHv2, timeout, retries, no telnet, RSA keys |
| Console & VTY Line Security | 5 | Exec-timeout, ACLs, AUX disable |
| SNMP Security | 5 | SNMPv3, no public/private, ACL restrictions |
| Logging & Monitoring | 5 | Syslog, buffer, timestamps, source interface |
| NTP Configuration | 3 | NTP server, authentication, source |
| Banner Configuration | 3 | Login, MOTD, exec banners |
| NAC / 802.1X | 12 | dot1x, MAB, RADIUS, auth order/priority/violation |
| Port Security & L2 Hardening | 9 | DHCP snooping, DAI, storm control, BPDU guard |
| Routing Protocol Security | 4 | OSPF/EIGRP/BGP authentication |
| General Hardening | 16 | Password encryption, HTTP disable, CDP, source-route |
| Access Control Lists | 2 | VTY ACL, SNMP ACL |
| Management Plane | 4 | CoPP, login block-for, login logging |

**Customize** by editing the YAML — add, remove, or modify rules to match your organization's policies.

---

## Architecture

```
┌─────────────────────────────────────────────────────┐
│                   Web Browser                        │
│              (Dashboard + Reports)                   │
└──────────────┬──────────────────────┬────────────────┘
               │ HTTP                  │ Download
┌──────────────▼──────────────────────▼────────────────┐
│              Flask Web Server (app.py)                │
│  ┌──────────┐  ┌────────────────┐  ┌──────────────┐ │
│  │   SSH    │  │   Compliance   │  │    Report     │ │
│  │Connector │  │   Checker      │  │  Generator    │ │
│  │(Netmiko) │  │(Regex Engine)  │  │ (PDF + CSV)   │ │
│  └────┬─────┘  └───────┬────────┘  └──────────────┘ │
└───────┼────────────────┼────────────────────────────-┘
        │                │
        │ SSH             │ YAML
        ▼                ▼
┌───────────────┐  ┌──────────────┐
│   Switches    │  │   Golden     │
│  (Pan India)  │  │  Template    │
│  via Bastion  │  │  (config/)   │
└───────────────┘  └──────────────┘
```

---

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `COMPLIANCE_MODE` | `demo` | `demo` for simulated data, `live` for real SSH |
| `PORT` | `5000` | Web server port |
| `MAX_SSH_WORKERS` | `10` | Max concurrent SSH connections |
| `FLASK_DEBUG` | `0` | Set to `1` for debug mode |
| `SECRET_KEY` | (random) | Flask session secret key |

---

## Reports

### PDF Report
- Executive summary with overall compliance %
- Compliance by region (table)
- Compliance by category (table)
- Top non-compliant rules (most frequent failures)
- Per-switch detailed findings with remediation steps

### CSV Summary
One row per switch: name, hostname, region, compliance %, severity counts

### CSV Detailed
One row per finding per switch: rule ID, description, severity, status, remediation

---

## Production Deployment

For production use on the bastion server:

```bash
# Use waitress (production WSGI server, included in requirements)
pip install waitress
waitress-serve --host=0.0.0.0 --port=5000 app:app

# Or use gunicorn (Linux)
gunicorn -w 4 -b 0.0.0.0:5000 app:app
```

**Security considerations:**
- Change `SECRET_KEY` to a strong random value
- Use environment variables for switch credentials (not plaintext in YAML)
- Restrict access to the dashboard (run behind a reverse proxy with auth)
- Use HTTPS in production

---

## Troubleshooting

| Issue | Solution |
|-------|----------|
| SSH timeout | Increase `timeout` in inventory.yaml, verify network path |
| Auth failed | Check credentials in inventory.yaml, verify TACACS/local auth |
| Module not found | Run `pip install -r requirements.txt` |
| PDF not generating | Install reportlab: `pip install reportlab` |
| Port in use | Change `PORT` env var: `set PORT=8080` |

---

## License

Internal use. Customize the golden template to match your organization's security policies and compliance requirements.
