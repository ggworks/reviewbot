import os
import re
import requests
from config import *
import lsp_utils.lsp as lsp


def should_skip_review(filename):
    # list of file extensions for which review should be skipped
    skip_extensions = ['.txt', '.json', '.xml', '.csv', '.md', '.log', '.ini', '.yml', '.pyc', '.class', '.cmake']

    asset_extensions = ['.png', '.jpg', '.jpeg', '.gif', '.svg', '.ico', '.eot', '.ttf', '.woff', '.woff2']

    # list of file names to be skipped
    skip_files = ['README.md', 'LICENSE', '.gitignore', 'package-lock.json', 'yarn.lock', 'Makefile', 'Dockerfile']

    # list of folders to be skipped
    skip_folders = ['__pycache__', '.git', '.vscode', 'node_modules', 'dist', 'build']

    # get file extension
    file_extension = os.path.splitext(filename)[-1]

    # get file name
    file_name = os.path.basename(filename)

    # check if the file is in a skip folder
    for folder in skip_folders:
        if folder in filename.split(os.path.sep):
            return True

    # check if file extension is in the skip list
    if file_extension in skip_extensions or file_name in skip_files:
        return True

    if file_extension in asset_extensions:
        return True

    return False

def download_file(repo_full_name, filename, commit_id):
    download_url = f"https://api.github.com/repos/{repo_full_name}/contents/{filename}?ref={commit_id}"
    
    # logger.info(f"download_file: {download_url}")
    headers = {
        "Authorization": f"token {GITHUB_API_TOKEN}",
        "Accept": "application/vnd.github.v3.raw",
    }
    response = requests.get(download_url, headers=headers)
    response.raise_for_status()  # Raise an exception if the request failed

    return response.text

def parse_diff(patch):
    # This regex will match the hunk headers, and capture the start line and line count of the new file
    hunk_header_regex = re.compile(r'@@ -\d+,\d+ \+(\d+),(\d+) @@')

    # This list will contain all the changed lines
    changed_lines = []

    for match in hunk_header_regex.finditer(patch):
        start_line = int(match.group(1))
        line_count = int(match.group(2))

        # Add all the lines in the hunk to the list
        changed_lines.append([start_line, start_line + line_count])

    return changed_lines


def get_language_type(filename):
    extension = filename.rsplit('.', 1)[-1].lower()

    language_types = {
        'py': 'python',
        'js': 'javascript',
        'java': 'java',
        'cpp': 'cpp',
        'css': 'css',
        'php': 'php',
        'ts': 'typescript',
        'tsx': 'typescript',
    }

    return language_types.get(extension, 'Unknown')


def is_range_overlapping(range1, line_range):
    return (range1["start"]["line"] <= line_range[1]) and (range1["end"]["line"] >= line_range[0])


def get_symbols_intersecting_with_range(symbols, line_range):
    intersecting_symbols = []

    for symbol in symbols:
        if not 'range' in symbol or not is_range_overlapping(symbol["range"], line_range):
            continue
        if symbol['kind'] in [lsp.SymbolKind.Function, lsp.SymbolKind.Method, lsp.SymbolKind.Constructor, lsp.SymbolKind.
                              Constant, lsp.SymbolKind.Variable, lsp.SymbolKind.Enum, lsp.SymbolKind.Struct]:
            intersecting_symbols.append([symbol])
            continue

        children_paths = get_symbols_intersecting_with_range(symbol["children"], line_range) if "children" in symbol else []
        if len(children_paths):
            for child_path in children_paths:
                new_path = [symbol]
                new_path.extend(child_path)
                intersecting_symbols.append(new_path)
        else:
            intersecting_symbols.append([symbol])

    return intersecting_symbols