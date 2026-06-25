#!/usr/bin/env python3

import argparse
import datetime
import json
import os
import re
import subprocess
import tempfile
import yaml

def parse_month_arg(value):
    try:
        year, month = value.split("-")
    except ValueError:
        raise argparse.ArgumentTypeError(
            "report date must be in YYYY-MM format"
        )

    if len(year) != 4 or len(month) != 2 or not year.isdigit() or not month.isdigit():
        raise argparse.ArgumentTypeError(
            "report date must be in YYYY-MM format"
        )

    month_int = int(month)
    if month_int < 1 or month_int > 12:
        raise argparse.ArgumentTypeError(
            "report month must be between 01 and 12"
        )

    return value


def run_git(repo_root, *args, capture_output=True):
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=capture_output,
        text=True,
        check=False,
    )


def verify_git_repo(repo_root, parser):
    result = run_git(repo_root, "rev-parse", "--is-inside-work-tree")
    if result.returncode != 0 or result.stdout.strip() != "true":
        parser.error(f"{repo_root} is not a git repository")

    result = run_git(repo_root, "branch", "--show-current")
    branch = result.stdout.strip()
    if result.returncode != 0 or branch != "main":
        parser.error(
            f"repository must have the main branch checked out, found: {branch or '<none>'}"
        )

    result = run_git(repo_root, "status", "--porcelain")
    if result.returncode != 0:
        parser.error("failed to query git status for repository")

    if result.stdout.strip():
        parser.error(
            "repository has local changes or untracked files; please clean or stash them before running"
        )


def get_commit_before(repo_root, dt, parser, description):
    cutoff = dt.strftime("%Y-%m-%d %H:%M:%S")
    result = run_git(
        repo_root,
        "rev-list",
        "-1",
        "--before",
        cutoff,
        "main",
    )
    if result.returncode != 0:
        parser.error(f"failed to resolve commit for {description}")

    commit = result.stdout.strip()
    if not commit:
        parser.error(
            f"could not find a commit on main before {cutoff} for {description}"
        )

    return commit


def get_month_snapshot_commits(repo_root, year_month, parser):
    year, month = map(int, year_month.split("-"))
    start_of_month = datetime.datetime(year, month, 1, 0, 0, 0)
    if month == 12:
        next_month = datetime.datetime(year + 1, 1, 1, 0, 0, 0)
    else:
        next_month = datetime.datetime(year, month + 1, 1, 0, 0, 0)

    beginning_commit = get_commit_before(
        repo_root,
        start_of_month,
        parser,
        f"beginning of {year_month}",
    )
    end_commit = get_commit_before(
        repo_root,
        next_month,
        parser,
        f"end of {year_month}",
    )

    return beginning_commit, end_commit


def read_frontmatter(file_path):
    with open(file_path, "r", encoding="utf-8") as handle:
        first_line = handle.readline()
        if not first_line.startswith("---"):
            return None

        frontmatter_lines = []
        for raw_line in handle:
            if raw_line.strip() == "---":
                break
            frontmatter_lines.append(raw_line)

    if not frontmatter_lines:
        return None

    frontmatter_text = "".join(frontmatter_lines)
    metadata = yaml.safe_load(frontmatter_text)

    if metadata is None:
        return {}
    if not isinstance(metadata, dict):
        return None

    return metadata


def load_proposal_frontmatters(repo_root):
    proposals_root = os.path.join(repo_root, "proposals")
    if not os.path.isdir(proposals_root):
        return []

    frontmatters = []
    for dirpath, _, filenames in os.walk(proposals_root):
        for filename in filenames:
            if not filename.endswith(".md"):
                continue
            file_path = os.path.join(dirpath, filename)
            frontmatter = read_frontmatter(file_path)
            if frontmatter is None:
                continue
            if frontmatter.get("draft") is True:
                continue
            raw_status = frontmatter.get("status")
            if raw_status is not None:
                frontmatter["_proposal_status"] = raw_status
            status = extract_proposal_implementation_status(file_path)
            frontmatter["status"] = status
            frontmatter["implementation_status"] = status
            frontmatters.append(frontmatter)

    return frontmatters


def extract_markdown_section(lines, heading):
    section_lines = []
    found_heading = False

    for raw_line in lines:
        line = raw_line.rstrip("\n").strip()
        if not line:
            if found_heading:
                section_lines.append("")
            continue

        if not found_heading:
            if not line.startswith("#"):
                continue
            parts = line.split(None, 1)
            if len(parts) < 2:
                continue
            if parts[1].strip() == heading:
                found_heading = True
            continue

        if line.startswith("#"):
            break
        section_lines.append(line)

    return section_lines if found_heading else None


def parse_markdown_table(lines):
    if not lines:
        return []

    # Search for a markdown table start inside the section.
    header_index = None
    for index in range(len(lines) - 1):
        if "|" in lines[index] and "|" in lines[index + 1]:
            separator_cells = [cell.strip() for cell in lines[index + 1].strip().strip("|").split("|")]
            if separator_cells and all(re.match(r'^:?-{3,}:?$', cell) for cell in separator_cells):
                header_index = index
                break

    if header_index is None:
        return []

    header_cells = [cell.strip() for cell in lines[header_index].strip().strip("|").split("|")]
    if not header_cells:
        return []

    if not header_cells[0]:
        header_cells[0] = ""

    rows = []
    for row_line in lines[header_index + 2:]:
        if not row_line.strip():
            break
        if "|" not in row_line:
            break

        row_cells = [cell.strip() for cell in row_line.strip().strip("|").split("|")]
        if len(row_cells) < len(header_cells):
            row_cells.extend([""] * (len(header_cells) - len(row_cells)))
        elif len(row_cells) > len(header_cells):
            row_cells = row_cells[: len(header_cells)]

        row = dict(zip(header_cells, row_cells))
        rows.append(row)

    return rows


def format_github_reference(cell_text):
    if not isinstance(cell_text, str):
        return str(cell_text)

    def replace_match(match):
        org, repo, number = match.group(1), match.group(2), match.group(3)
        url = match.group(0)
        return f"[{org}/{repo}#{number}]({url})"

    return re.sub(
        r'https?://github\.com/([^/\s]+)/([^/\s]+)/(?:issues|pull)/(\d+)',
        replace_match,
        cell_text,
    )


def render_markdown_table(rows):
    if not rows:
        return []

    headers = list(rows[0].keys())
    table_lines = ["| " + " | ".join(headers) + " |", "|" + "|".join(["---"] * len(headers)) + "|"]
    for row in rows:
        cells = [format_github_reference(row.get(header, "") or "") for header in headers]
        table_lines.append("| " + " | ".join(cells) + " |")

    return table_lines


def extract_proposal_implementation_status(file_path):
    with open(file_path, "r", encoding="utf-8") as handle:
        lines = handle.readlines()

    section = extract_markdown_section(lines, "Implementation Status")
    if section is None:
        return []

    return parse_markdown_table(section)


def get_normative_updates(repo_root, beginning_commit, end_commit):
    result = run_git(
        repo_root,
        "log",
        "--oneline",
        "--pretty=format:%s",
        f"{beginning_commit}..{end_commit}",
        "--",
        "spec/*.tex",
    )
    if result.returncode != 0:
        return []
    updates = result.stdout.strip().split('\n') if result.stdout.strip() else []
    # Convert (#number) to ([#number](link))
    repo_url = "https://github.com/hlsl-tc57/tc57/pull/"
    for i, update in enumerate(updates):
        updates[i] = re.sub(r'\(#(\d+)\)', rf'([#\1]({repo_url}\1))', update)
    return updates


def build_proposal_index(proposals):
    return {proposal.get("title", ""): proposal for proposal in proposals}


def get_proposal_field(proposal, field, default=None):
    params = proposal.get("params")
    if isinstance(params, dict) and field in params:
        return params[field]
    if field == "status":
        if "_proposal_status" in proposal:
            return proposal["_proposal_status"]
        if field in proposal and not isinstance(proposal[field], list):
            return proposal[field]
        return default
    if field in proposal:
        return proposal[field]
    return default


def format_proposal_entry(proposal):
    title = get_proposal_field(proposal, "title", "<untitled>")
    status = get_proposal_field(proposal, "status", "<unknown>")
    authors = get_proposal_field(proposal, "authors")
    if isinstance(authors, list):
        author_names = []
        for author in authors:
            if isinstance(author, dict):
                author_names.extend(author.values())
            elif isinstance(author, str):
                author_names.append(author)
            else:
                author_names.append(str(author))
        authors = ", ".join(author_names)
    elif authors is None:
        authors = ""
    else:
        authors = str(authors)
    return f"- **{title}** ({status})" + (f" — {authors}" if authors else "")


def build_monthly_proposal_report(month, beginning, end, normative_updates):
    beginning_index = build_proposal_index(beginning)
    end_index = build_proposal_index(end)

    all_titles = sorted(set(beginning_index) | set(end_index))

    new_proposals = [end_index[t] for t in all_titles if t not in beginning_index]
    removed_proposals = [beginning_index[t] for t in all_titles if t not in end_index]
    status_changes = []

    for title in sorted(set(beginning_index) & set(end_index)):
        before = beginning_index[title]
        after = end_index[title]
        before_status = get_proposal_field(before, "status")
        after_status = get_proposal_field(after, "status")
        if before_status != after_status:
            status_changes.append((title, before_status or "<none>", after_status or "<none>"))

    lines = ["---",f"title: Monthly Report for {month}",
            "date: " + datetime.datetime.now().strftime('%Y-%m-%d'),
             "---", ""]

    if new_proposals:
        lines.append("## New proposals during the month")
        lines.extend(format_proposal_entry(p) for p in new_proposals)
        lines.append("")

    if removed_proposals:
        lines.append("## Proposals no longer active at month end")
        lines.extend(format_proposal_entry(p) for p in removed_proposals)
        lines.append("")

    if status_changes:
        lines.append("## Status changes")
        for title, before_status, after_status in status_changes:
            lines.append(f"- **{title}**: {before_status} → {after_status}")
        lines.append("")

    if normative_updates:
        lines.append("## Normative Updates")
        lines.extend(f"- {update}" for update in normative_updates)
        lines.append("")

    lines.append("## Implementation Status")
    for title in all_titles:
        proposal = end_index.get(title, beginning_index.get(title))
        status = get_proposal_field(proposal, "status", "<unknown>")
        lines.append(f"### {title}")
        lines.append(f"State: {status}")
        implementation_rows = proposal.get("implementation_status", [])
        if implementation_rows:
            lines.extend(render_markdown_table(implementation_rows))
        else:
            lines.append("No status available")
        lines.append("")

    if not (new_proposals or removed_proposals or status_changes or normative_updates):
        lines.append("No proposal changes detected between the beginning and end of the month.")

    return "\n".join(lines)


def parse_args():
    parser = argparse.ArgumentParser(
        description="Generate monthly blog content against the tc57 repository."
    )
    parser.add_argument(
        "--repo",
        required=True,
        help="Path to the tc57 repository root.",
    )
    parser.add_argument(
        "month",
        type=parse_month_arg,
        help="Monthly report date in YYYY-MM format.",
    )

    args = parser.parse_args()

    repo_root = os.path.abspath(args.repo)
    if not os.path.isdir(repo_root):
        parser.error(f"--repo path does not exist or is not a directory: {repo_root}")

    verify_git_repo(repo_root, parser)

    return parser, repo_root, args.month


def main():
    parser, repo_root, month = parse_args()
    beginning_commit, end_commit = get_month_snapshot_commits(repo_root, month, parser)

    with (tempfile.TemporaryDirectory(prefix="tc57-monthly-begin-") as beginning_tree,
          tempfile.TemporaryDirectory(prefix="tc57-monthly-end-") as end_tree):
        result = run_git(repo_root, "worktree", "add", "--detach", beginning_tree, beginning_commit)
        if result.returncode != 0:
            raise RuntimeError(
                f"failed to create temporary worktree for beginning of month: {result.stderr.strip()}"
            )

        result = run_git(repo_root, "worktree", "add", "--detach", end_tree, end_commit)
        if result.returncode != 0:
            raise RuntimeError(
                f"failed to create temporary worktree for end of month: {result.stderr.strip()}"
            )

        beginning_proposals = load_proposal_frontmatters(beginning_tree)
        end_proposals = load_proposal_frontmatters(end_tree)

    beginning_proposals.sort(key=lambda item: item.get("title", ""))
    end_proposals.sort(key=lambda item: item.get("title", ""))

    normative_updates = get_normative_updates(repo_root, beginning_commit, end_commit)

    report_text = build_monthly_proposal_report(month, beginning_proposals, end_proposals, normative_updates)
    print(report_text)


if __name__ == "__main__":
    main()
