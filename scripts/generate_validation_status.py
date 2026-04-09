#!/usr/bin/env python3
"""Generate validation status dashboard for experiment documents.

Scans all experiment overview.md files for validation frontmatter and
experiment status admonitions, then produces a markdown dashboard at
docs/reference/validation-status.md.

Usage:
    python3 scripts/generate_validation_status.py
"""

import os
import re
from datetime import datetime, timedelta

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS_DIR = os.path.join(REPO_ROOT, "docs")
OUTPUT_PATH = os.path.join(DOCS_DIR, "reference", "validation-status.md")

STALENESS_DAYS = 90

EXPERIMENT_PATHS = [
    ("App Service", "Memory Pressure", "app-service/memory-pressure/overview.md"),
    ("App Service", "procfs Interpretation", "app-service/procfs-interpretation/overview.md"),
    ("App Service", "Slow Requests", "app-service/slow-requests/overview.md"),
    ("App Service", "Zip vs Container", "app-service/zip-vs-container/overview.md"),
    ("Functions", "Flex Consumption Storage", "functions/flex-consumption-storage/overview.md"),
    ("Functions", "Cold Start", "functions/cold-start/overview.md"),
    ("Functions", "Dependency Visibility", "functions/dependency-visibility/overview.md"),
    ("Container Apps", "Ingress SNI / Host Header", "container-apps/ingress-sni-host-header/overview.md"),
    ("Container Apps", "Private Endpoint FQDN vs IP", "container-apps/private-endpoint-fqdn-vs-ip/overview.md"),
    ("Container Apps", "Startup Probes", "container-apps/startup-probes/overview.md"),
]

VALIDATION_METHODS = ["az_cli", "bicep", "terraform"]


def parse_frontmatter(filepath):
    """Parse YAML frontmatter manually (no PyYAML dependency)."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    # Extract frontmatter between --- fences
    match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
    if not match:
        return {}

    fm_text = match.group(1)
    validation = {}

    for method in VALIDATION_METHODS:
        method_match = re.search(
            rf"{method}:\s*\n"
            rf"\s+last_tested:\s*(.*?)\n"
            rf"\s+result:\s*(.*?)(?:\n|$)",
            fm_text,
        )
        if method_match:
            last_tested_raw = method_match.group(1).strip()
            result_raw = method_match.group(2).strip()

            last_tested = None
            if last_tested_raw and last_tested_raw != "null":
                try:
                    last_tested = datetime.strptime(last_tested_raw, "%Y-%m-%d").date()
                except ValueError:
                    pass

            validation[method] = {
                "last_tested": last_tested,
                "result": result_raw if result_raw else "not_tested",
            }
        else:
            validation[method] = {"last_tested": None, "result": "not_tested"}

    return validation


def detect_experiment_status(filepath):
    """Detect experiment status from admonition text."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    if re.search(r'!!! info "Status: Published"', content):
        return "Published"
    elif re.search(r'!!! info "Status: Draft', content):
        return "Draft"
    elif re.search(r'!!! info "Status: Planned"', content):
        return "Planned"
    return "Unknown"


def result_emoji(result, last_tested):
    """Return emoji for validation result with staleness check."""
    today = datetime.now().date()

    if result == "pass":
        if last_tested and (today - last_tested) > timedelta(days=STALENESS_DAYS):
            return "⚠️ stale"
        return "✅ pass"
    elif result == "fail":
        return "❌ fail"
    else:
        return "➖"


def get_latest_date(validation):
    """Get the most recent test date across all methods."""
    dates = []
    for method in VALIDATION_METHODS:
        if method in validation and validation[method]["last_tested"]:
            dates.append(validation[method]["last_tested"])
    return max(dates) if dates else None


def staleness_label(latest_date):
    """Return staleness status label."""
    if latest_date is None:
        return "Not tested"

    today = datetime.now().date()
    days = (today - latest_date).days

    if days > STALENESS_DAYS:
        return f"⚠️ {days}d ago"
    elif days == 0:
        return "✅ Today"
    else:
        return f"✅ {days}d ago"


def generate_dashboard():
    """Generate the validation status dashboard markdown."""
    today = datetime.now().strftime("%Y-%m-%d")

    lines = [
        "---",
        "hide:",
        "  - toc",
        "---",
        "",
        "# Validation Status",
        "",
        f"*Auto-generated on {today} by `scripts/generate_validation_status.py`. Do not edit manually.*",
        "",
        "## Overview",
        "",
        "This dashboard tracks when each experiment was last validated against a real Azure environment.",
        "",
        f"- **Staleness threshold**: {STALENESS_DAYS} days",
        "- **Validation methods**: `az_cli` (manual CLI), `bicep` (IaC), `terraform` (IaC)",
        "",
        "## Experiment Validation Status",
        "",
        "| Experiment | Service | Status | az_cli | bicep | terraform | Last Tested | Staleness |",
        "|---|---|---|---|---|---|---|---|",
    ]

    summary = {"total": 0, "published": 0, "draft": 0, "planned": 0, "tested": 0, "stale": 0}

    for service, name, rel_path in EXPERIMENT_PATHS:
        filepath = os.path.join(DOCS_DIR, rel_path)
        summary["total"] += 1

        if not os.path.exists(filepath):
            lines.append(f"| {name} | {service} | ❓ Missing | ➖ | ➖ | ➖ | — | — |")
            continue

        validation = parse_frontmatter(filepath)
        status = detect_experiment_status(filepath)

        if status == "Published":
            summary["published"] += 1
        elif status == "Draft":
            summary["draft"] += 1
        elif status == "Planned":
            summary["planned"] += 1

        az_cli_info = validation.get("az_cli", {"last_tested": None, "result": "not_tested"})
        bicep_info = validation.get("bicep", {"last_tested": None, "result": "not_tested"})
        terraform_info = validation.get("terraform", {"last_tested": None, "result": "not_tested"})

        az_emoji = result_emoji(az_cli_info["result"], az_cli_info["last_tested"])
        bicep_emoji = result_emoji(bicep_info["result"], bicep_info["last_tested"])
        terraform_emoji = result_emoji(terraform_info["result"], terraform_info["last_tested"])

        latest = get_latest_date(validation)
        last_str = str(latest) if latest else "—"
        stale_str = staleness_label(latest)

        if latest:
            summary["tested"] += 1
            if (datetime.now().date() - latest).days > STALENESS_DAYS:
                summary["stale"] += 1

        # Link to experiment page
        doc_link = rel_path.replace("overview.md", "overview.md")
        lines.append(
            f"| [{name}](../{doc_link}) | {service} | {status} | {az_emoji} | {bicep_emoji} | {terraform_emoji} | {last_str} | {stale_str} |"
        )

    lines.extend([
        "",
        "## Summary",
        "",
        f"| Metric | Count |",
        f"|---|---|",
        f"| Total experiments | {summary['total']} |",
        f"| Published | {summary['published']} |",
        f"| Draft | {summary['draft']} |",
        f"| Planned | {summary['planned']} |",
        f"| Tested (any method) | {summary['tested']} |",
        f"| Stale (>{STALENESS_DAYS}d) | {summary['stale']} |",
        "",
        "## Evidence Level Legend",
        "",
        "| Emoji | Meaning |",
        "|---|---|",
        "| ✅ pass | Validated successfully |",
        "| ❌ fail | Validation failed |",
        "| ⚠️ stale | Passed but older than 90 days |",
        "| ➖ | Not tested |",
        "",
    ])

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Dashboard generated: {OUTPUT_PATH}")
    print(f"  Total experiments: {summary['total']}")
    print(f"  Published: {summary['published']}, Draft: {summary['draft']}, Planned: {summary['planned']}")
    print(f"  Tested: {summary['tested']}, Stale: {summary['stale']}")


if __name__ == "__main__":
    generate_dashboard()
