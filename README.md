# BlockRun Usage Reports for OpenClaw Router

Self-contained toolkit that scans a folder of daily `usage-YYYY-MM-DD.jsonl`
log files and produces a single, fully offline HTML report with:

- **Aggregated overview** — KPIs, charts, and model breakdown across all days
- **Per-day sections** — each with its own charts and stats
- **Sticky sidebar navigation** — jump to any day instantly
- **No external runtime dependencies** — pure Python 3 stdlib + one CDN JS file

---

# Screenshot

<img width="1670" height="890" alt="Screenshot from 2026-02-26 17-29-28" src="https://github.com/user-attachments/assets/53cb75c7-6fca-412d-8122-008480368752" />

---

## Files

| File | Purpose |
|------|---------|
| `generate_reports.py` | Main report generator |
| `blockrun_cron.sh`    | Cron wrapper (logging, rotation, error handling) |
| `install_cron.sh`     | Installs / removes the cron job |
| `sample_report.html`  | Pre-generated sample report |

---

## Quick Start

```bash
# 1. Clone / unpack to your server
git clone https://github.com/fabgoodvibes/clawrouter_reports
cd clawrouter_reports

# 2. Generate a report right now
python3 generate_reports.py /home/agent/.openclaw/blockrun/logs/
# → writes report.html in the log directory

# Custom output path
python3 generate_reports.py /home/agent/.openclaw/blockrun/logs/ /home/agent/.openclaw/workspace/report.html

# 3. Install the hourly cron job
chmod +x install_cron.sh blockrun_cron.sh
./install_cron.sh

# Daily at 06:30 instead
CRON_SCHEDULE="30 6 * * *" ./install_cron.sh

# Remove the cron job
./install_cron.sh --remove
```

---

## Configuration

All settings in `blockrun_cron.sh` can also be overridden via environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `BLOCKRUN_LOG_DIR`   | `/home/agent/.openclaw/blockrun/logs/` | Directory with `.jsonl` files |
| `BLOCKRUN_OUTPUT`    | `/home/agent/.openclaw/workspace/report.html` | Output report path |
| `BLOCKRUN_GENERATOR` | `<script dir>/generate_reports.py` | Path to the Python script |
| `BLOCKRUN_PYTHON`    | `python3`                        | Python interpreter to use |
| `BLOCKRUN_KEEP`      | `21`                             | Archived reports to keep (0 = disable) |
| `BLOCKRUN_CRON_LOG`  | `$LOG_DIR/cron.log`              | Cron run log (`""` to disable) |

Example — override at cron install time:
```bash
BLOCKRUN_LOG_DIR=/data/logs \
BLOCKRUN_OUTPUT=/srv/www/report.html \
BLOCKRUN_KEEP=14 \
./install_cron.sh
```

---

## Log File Format

Each line in a `usage-YYYY-MM-DD.jsonl` file should be a JSON object.

**Required fields:**

```json
{
  "timestamp":    "2026-02-25T10:30:00.000Z",
  "model":        "xai/grok-code-fast-1",
  "tier":         "MEDIUM",
  "cost":         0.01034,
  "baselineCost": 0.19560
}
```

**Optional fields** (gracefully omitted from the report if absent):

```json
{
  "savings":      1,
  "latencyMs":    15800,
  "inputTokens":  3241,
  "outputTokens": 847
}
```

> When `inputTokens` and `outputTokens` are present, a **Tokens** column appears
> in the Model Breakdown table showing total tokens with an `Xk↑ Yk↓` input/output
> breakdown. The column is automatically hidden when no token data is found.

Invalid or malformed lines are silently skipped.

---

## Report Archiving

When the cron job runs, the previous `report.html` is copied to:

```
<output_dir>/archive/report.YYYY-MM-DD_HH-MM.html
```

Only the `BLOCKRUN_KEEP` (default: 21) most recent archives are retained.
Set `BLOCKRUN_KEEP=0` to disable archiving.

---

## Requirements

- Python 3.8+
- Internet access for the report viewer (loads Chart.js from jsDelivr CDN)
  - For fully offline use, download Chart.js and update the `<script>` src in `generate_reports.py`

---

## License

Copyright 2026 Fabio Pedrazzoli Grazioli

Licensed under the MIT License

https://opensource.org/license/mit

Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated documentation files (the "Software"), to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software, and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
