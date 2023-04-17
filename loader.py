import logging
import os
import importlib
import re
from pathlib import Path

# noinspection PyPackageRequirements
from telegram.ext import Application, BaseHandler

from config import config

logger = logging.getLogger(__name__)


def read_manifest(manifest_path: Path):
    if not manifest_path:
        return

    try:
        with open(manifest_path, 'r') as f:
            manifest_str = f.read()
    except FileNotFoundError:
        logger.debug('manifest <%s> not found', manifest_path)
        return

    if not manifest_str.strip():
        logger.debug('manifest <%s> is empty', manifest_path)
        return

    manifest_str = manifest_str.replace('\r\n', '\n')
    manifest_lines = manifest_str.split('\n')

    modules_list = list()
    for line in manifest_lines:
        line = re.sub(r'(?:\s+)?#.*(?:\n|$)', '', line)  # remove comments from the line
        if line.strip():  # ignore empty lines
            items = line.split()  # split on spaces. We will consider only the first word
            modules_list.append(items[0])  # tuple: (module_to_import, [callbacks_list])

    return modules_list


def scan_modules_to_import(plugins_directory: Path, manifest_file_name="manifest"):
    """A text file named "manifest" can be placed in the dir we are importing the handlers from.
    It can contain the list of the files to import, the bot will import only these
    modules as ordered in the manifest file.
    Inline comments are allowed, they must start by #"""

    base_import_path = plugins_directory.parts[-1]

    paths_to_import = list()

    manifest_file_path = plugins_directory / manifest_file_name
    # manifest_file_path = os.path.join(directory, manifest_file_name)
    manifest_modules = read_manifest(manifest_file_path)

    if manifest_modules:
        logger.debug(f"manifest modules: {', '.join(manifest_modules)}")

        # build the base import path of the plugins/jobs directory
        logger.debug(f"target dir path: {base_import_path}")

        for module in manifest_modules:
            import_path = f"{base_import_path}.{module}"

            logger.debug(f'module to import: {import_path}')

            paths_to_import.append(import_path)
    else:
        for file_path in sorted(Path(plugins_directory).rglob('*.py')):
            if file_path.is_dir():
                continue

            relative_file_path = file_path.relative_to(plugins_directory)
            # 'relative_file_path.parts' would be for example ('subdir', 'plugin.py')

            import_path_parts = [file_path_parts.strip(".py") for file_path_parts in relative_file_path.parts]

            import_path = f"{base_import_path}." + '.'.join(import_path_parts)

            paths_to_import.append(import_path)

    return paths_to_import


def load_modules(app: Application, plugins_directory: str, manifest_file_name="manifest"):
    plugins_directory = Path(plugins_directory)

    paths_to_import = scan_modules_to_import(plugins_directory, manifest_file_name)

    for import_path in paths_to_import:
        logger.debug('importing module: %s', import_path)
        module = importlib.import_module(import_path)

        for name in vars(module).keys():
            if name != "HANDLERS":
                continue

            handlers_list = getattr(module, name)
            for handler, group in handlers_list:
                if not isinstance(handler, BaseHandler):
                    continue

                app.add_handler(handler, group)
                logger.debug(f"loading {type(handler).__name__}(handler={import_path}.{handler.callback.__name__}, group={group})")
