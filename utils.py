import os


def should_skip_review(filename):
    # list of file extensions for which review should be skipped
    skip_extensions = ['.txt', '.json', '.xml', '.csv', '.md', '.log', '.ini', '.yml', '.pyc', '.class']

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
