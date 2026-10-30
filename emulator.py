# Original module: vfs
# Загрузка виртуальной файловой системы из XML в память.

import base64
import binascii
import getpass
import time
from dataclasses import dataclass, field
import xml.etree.ElementTree as element_tree


DEFAULT_OWNER = "user"
DEFAULT_GROUP = "users"


def default_owner():
    # Возвращает начального владельца из ОС или запасное имя user.
    try:
        return getpass.getuser()
    except (KeyError, OSError, ImportError):
        return DEFAULT_OWNER


@dataclass
class File:
    # Виртуальный файл: байты, владелец, группа и временные метки.

    name: str
    data: bytes
    owner: str = field(default_factory=default_owner)
    group: str = DEFAULT_GROUP
    accessed: float = field(default_factory=time.time)
    modified: float = field(default_factory=time.time)


@dataclass
class Directory:
    # Виртуальный каталог: дочерние узлы, владелец и временные метки.

    name: str
    children: dict = field(default_factory=dict)
    owner: str = field(default_factory=default_owner)
    group: str = DEFAULT_GROUP
    accessed: float = field(default_factory=time.time)
    modified: float = field(default_factory=time.time)


class VFSError(Exception):
    # Ошибка чтения или формата VFS.
    pass


def validate_text(text):
    # Запрещает текст вне элемента file, кроме пробельных символов.
    if text and text.strip():
        raise VFSError("Текст должен находиться внутри элемента file")


def validate_name(name):
    # Проверяет непустое имя без разделителей и специальных компонентов.
    if not name.strip() or name in (".", ".."):
        raise VFSError(f"Недопустимое имя: {name!r}")
    if "/" in name or "\\" in name:
        raise VFSError(f"Недопустимое имя: {name!r}")


def validate_child(element, directory):
    # Проверяет тег, имя, атрибуты и уникальность вложенного элемента.
    if element.tag not in ("directory", "file"):
        raise VFSError(f"Неизвестный элемент: {element.tag}")
    name = element.get("name", "")
    validate_name(name)
    if name in directory.children:
        raise VFSError(f"Повторяющееся имя: {name}")
    allowed = {"name"}
    if element.tag == "file":
        allowed.add("encoding")
    if set(element.attrib) - allowed:
        raise VFSError(f"Неизвестный атрибут у {name}")
    validate_text(element.tail)
    return name


def decode_base64(text, name):
    # Декодирует base64 с пробельными символами или сообщает об ошибке.
    try:
        return base64.b64decode("".join(text.split()), validate=True)
    except (binascii.Error, ValueError) as error:
        raise VFSError(f"Неверный base64 в файле {name}") from error


def read_file(element, name):
    # Читает текстовый или двоичный файл без вложенных XML-элементов.
    if len(element):
        raise VFSError(f"Файл {name} не может содержать элементы XML")
    encoding = element.get("encoding", "text")
    text = element.text or ""
    if encoding == "text":
        data = text.encode("utf-8")
    elif encoding == "base64":
        data = decode_base64(text, name)
    else:
        raise VFSError(f"Неизвестная кодировка: {encoding}")
    return File(name, data)


def read_directory(element, name):
    # Рекурсивно строит дерево каталогов и файлов в памяти.
    directory = Directory(name)
    validate_text(element.text)
    for child in element:
        child_name = validate_child(child, directory)
        if child.tag == "directory":
            node = read_directory(child, child_name)
        else:
            node = read_file(child, child_name)
        directory.children[child_name] = node
    return directory


def load_vfs(path):
    # Читает XML, возвращает корень, не изменяя исходный файл.
    try:
        element = element_tree.parse(path).getroot()
    except FileNotFoundError as error:
        raise VFSError(f"Файл не найден: {path}") from error
    except (element_tree.ParseError, UnicodeError, ValueError) as error:
        raise VFSError(f"Неверный формат XML: {error}") from error
    except OSError as error:
        raise VFSError(f"Не удалось прочитать VFS: {error}") from error
    if element.tag != "vfs" or element.attrib:
        raise VFSError("Корневой элемент должен быть <vfs> без атрибутов")
    try:
        return read_directory(element, "/")
    except RecursionError as error:
        raise VFSError("Слишком большая вложенность папок") from error


def count_nodes(directory):
    # Считает папки и файлы без учёта корневой папки.
    directories = 0
    files = 0
    for node in directory.children.values():
        if isinstance(node, Directory):
            nested_dirs, nested_files = count_nodes(node)
            directories += 1 + nested_dirs
            files += nested_files
        else:
            files += 1
    return directories, files


# Original module: session
# Состояние эмулятора и разрешение путей внутри VFS.

from dataclasses import dataclass, field
import time


ROOT_PATH = "/"
CURRENT_COMPONENT = "."
PARENT_COMPONENT = ".."


class CommandError(Exception):
    # Ошибка аргументов или операции над виртуальной файловой системой.
    pass


@dataclass
class ShellState:
    # Корень VFS, текущий каталог и начало работы эмулятора.

    root: Directory
    cwd: str = ROOT_PATH
    previous_cwd: str = ROOT_PATH
    started: float = field(default_factory=time.monotonic)


def require_directory(node, path):
    # Возвращает каталог или сообщает о попытке прохода через файл.
    if not isinstance(node, Directory):
        raise CommandError(f"{path}: not a directory")
    return node


def node_at(root, components):
    # Находит узел по уже проверенным компонентам абсолютного пути.
    node = root
    for name in components:
        node = node.children[name]
    return node


def walk_path(root, components, original):
    # Проходит путь последовательно, проверяя каждый промежуточный узел.
    node = root
    resolved = []
    for name in components:
        require_directory(node, original)
        if name in ("", CURRENT_COMPONENT):
            continue
        if name == PARENT_COMPONENT:
            if resolved:
                resolved.pop()
            node = node_at(root, resolved)
            continue
        if name not in node.children:
            raise CommandError(f"{original}: no such file or directory")
        node = node.children[name]
        resolved.append(name)
    return ROOT_PATH + ROOT_PATH.join(resolved), node


def resolve_path(state, path):
    # Разрешает абсолютный или относительный POSIX-путь без доступа к ОС.
    if not path:
        raise CommandError("empty path")
    components = path.split(ROOT_PATH)
    if not path.startswith(ROOT_PATH):
        components = state.cwd.split(ROOT_PATH) + components
    return walk_path(state.root, components, path)


# Original module: options
# Разбор аргументов встроенных команд без завершения REPL.

import getopt


EMPTY_COUNT = 0
SINGLE_OPERAND = 1


def parse_options(args, short_options="", long_options=()):
    # Разбирает опции; -- завершает опции, ошибки становятся CommandError.
    try:
        return getopt.gnu_getopt(args, short_options, list(long_options))
    except getopt.GetoptError as error:
        raise CommandError(str(error)) from error


def require_operands(paths):
    # Требует хотя бы один файловый операнд.
    if not paths:
        raise CommandError("missing operand")


def require_no_arguments(args):
    # Запрещает аргументы команды, не имеющей параметров.
    if args:
        raise CommandError("too many arguments")


def single_path(args, default):
    # Возвращает единственный операнд или значение по умолчанию.
    _, paths = parse_options(args)
    if len(paths) > SINGLE_OPERAND:
        raise CommandError("too many arguments")
    return paths[0] if paths else default


def nonnegative_count(value):
    # Преобразует число строк в целое неотрицательное значение.
    try:
        number = int(value)
    except ValueError as error:
        raise CommandError(f"invalid line count: {value}") from error
    if number < EMPTY_COUNT:
        raise CommandError(f"invalid line count: {value}")
    return number


# Original module: commands
# Основные команды UNIX-подобной оболочки над VFS в памяти.

from datetime import datetime, timezone
import time


DEFAULT_HEAD_LINES = 10
SECONDS_PER_MINUTE = 60
MINUTES_PER_HOUR = 60
PREVIOUS_DIRECTORY = "-"


def list_entries(node, path, show_all):
    # Возвращает отсортированные элементы каталога или сам файл.
    if not isinstance(node, Directory):
        return [(path, node)]
    entries = sorted(node.children.items())
    if show_all:
        return entries
    return [(name, child) for name, child in entries
            if not name.startswith(".")]


def format_entry(name, node, long_format):
    # Форматирует имя либо тип, владельца, группу, размер и время UTC.
    if not long_format:
        return name
    kind = "d" if isinstance(node, Directory) else "-"
    size = 0 if isinstance(node, Directory) else len(node.data)
    modified = datetime.fromtimestamp(node.modified, timezone.utc)
    stamp = modified.isoformat(timespec="seconds")
    return f"{kind} {node.owner} {node.group} {size} {stamp} {name}"


def command_ls(state, args):
    # Выводит каталог или файл; поддерживает -a, -l и несколько путей.
    options, paths = parse_options(args, "al")
    flags = {option for option, _ in options}
    paths = paths or [state.cwd]
    errors = []
    for path in paths:
        try:
            _, node = resolve_path(state, path)
            if len(paths) > SINGLE_OPERAND:
                print(f"{path}:")
            for name, child in list_entries(node, path, "-a" in flags):
                print(format_entry(name, child, "-l" in flags))
        except CommandError as error:
            errors.append(str(error))
    if errors:
        raise CommandError("; ".join(errors))


def command_cd(state, args):
    # Меняет каталог; без пути переходит в /, cd - возвращает предыдущий.
    if args == [PREVIOUS_DIRECTORY]:
        path = state.previous_cwd
    else:
        path = single_path(args, "/")
    canonical, node = resolve_path(state, path)
    require_directory(node, path)
    state.previous_cwd, state.cwd = state.cwd, canonical
    if args == [PREVIOUS_DIRECTORY]:
        print(state.cwd)


def read_text(state, path):
    # Возвращает UTF-8-текст файла; каталоги и двоичные данные запрещены.
    _, node = resolve_path(state, path)
    if isinstance(node, Directory):
        raise CommandError(f"{path}: is a directory")
    try:
        return node.data.decode("utf-8")
    except UnicodeError as error:
        raise CommandError(f"{path}: not a UTF-8 text file") from error


def first_lines(text, count):
    # Возвращает первые строки, считая разделителем только символ LF.
    if count == EMPTY_COUNT:
        return ""
    parts = text.split("\n")
    result = "\n".join(parts[:count])
    if len(parts) > count:
        result += "\n"
    return result


def output_files(state, paths, line_count=None):
    # Выводит доступные текстовые файлы, сохраняя сведения об ошибках.
    errors = []
    for path in paths:
        try:
            text = read_text(state, path)
            if line_count is not None:
                text = first_lines(text, line_count)
                if len(paths) > SINGLE_OPERAND:
                    print(f"==> {path} <==")
            print(text, end="")
        except CommandError as error:
            errors.append(str(error))
    if errors:
        raise CommandError("; ".join(errors))


def command_cat(state, args):
    # Выводит содержимое одного или нескольких UTF-8-файлов.
    _, paths = parse_options(args)
    require_operands(paths)
    output_files(state, paths)


def command_head(state, args):
    # Выводит первые 10 строк или число строк из -n/--lines.
    options, paths = parse_options(args, "n:", ("lines=",))
    require_operands(paths)
    count = DEFAULT_HEAD_LINES
    for _, value in options:
        count = nonnegative_count(value)
    output_files(state, paths, count)


def command_uptime(state, args):
    # Выводит время работы эмулируемой ОС с момента запуска приложения.
    require_no_arguments(args)
    elapsed = int(time.monotonic() - state.started)
    minutes, seconds = divmod(elapsed, SECONDS_PER_MINUTE)
    hours, minutes = divmod(minutes, MINUTES_PER_HOUR)
    print(f"up {hours:02}:{minutes:02}:{seconds:02}")


READ_COMMANDS = {
    "ls": command_ls,
    "cd": command_cd,
    "uptime": command_uptime,
    "cat": command_cat,
    "head": command_head,
}


# Original module: mutations
# Команды этапа 5: изменение владельца и временных меток только в памяти.

import re
import time


IDENTIFIER_PATTERN = r"[A-Za-z_][A-Za-z0-9_.-]*[$]?|[0-9]+"


def parse_ownership(value):
    # Разбирает OWNER или OWNER:GROUP без обращения к пользователям ОС.
    owner, separator, group = value.partition(":")
    if re.fullmatch(IDENTIFIER_PATTERN, owner) is None:
        raise CommandError(f"invalid owner: {value}")
    if separator and re.fullmatch(IDENTIFIER_PATTERN, group) is None:
        raise CommandError(f"invalid group: {value}")
    return owner, group if separator else None


def apply_ownership(state, paths, owner, group):
    # Меняет владельца узлов, продолжая обработку после ошибочного пути.
    errors = []
    for path in paths:
        try:
            _, node = resolve_path(state, path)
            node.owner = owner
            if group is not None:
                node.group = group
        except CommandError as error:
            errors.append(str(error))
    if errors:
        raise CommandError("; ".join(errors))


def command_chown(state, args):
    # Меняет владельца и необязательную группу файлов или каталогов.
    _, operands = parse_options(args)
    if len(operands) <= SINGLE_OPERAND:
        raise CommandError("usage: chown OWNER[:GROUP] PATH ...")
    owner, group = parse_ownership(operands[0])
    apply_ownership(state, operands[1:], owner, group)


def find_or_create_file(state, path, no_create):
    # Находит узел или создаёт пустой файл в существующем каталоге.
    parent_path, separator, name = path.rpartition("/")
    if name in ("", ".", ".."):
        _, node = resolve_path(state, path)
        return node
    try:
        validate_name(name)
    except VFSError as error:
        raise CommandError(str(error)) from error
    if not separator:
        parent_path = state.cwd
    elif not parent_path:
        parent_path = "/"
    _, parent = resolve_path(state, parent_path)
    require_directory(parent, parent_path)
    if name in parent.children:
        return parent.children[name]
    if no_create:
        return None
    node = File(name, b"")
    parent.children[name] = node
    return node


def update_timestamps(node, timestamp, access_only, modified_only):
    # Обновляет время доступа, модификации или обе метки без потери данных.
    if not modified_only or access_only:
        node.accessed = timestamp
    if not access_only or modified_only:
        node.modified = timestamp


def touch_paths(state, paths, flags):
    # Обрабатывает пути touch в памяти, продолжая после ошибок операнда.
    errors = []
    timestamp = time.time()
    for path in paths:
        try:
            node = find_or_create_file(state, path, "-c" in flags)
            if node is not None:
                update_timestamps(node, timestamp,
                                  "-a" in flags, "-m" in flags)
        except CommandError as error:
            errors.append(str(error))
    if errors:
        raise CommandError("; ".join(errors))


def command_touch(state, args):
    # Создаёт файлы и обновляет метки: -a, -m, -c.
    options, paths = parse_options(args, "amc")
    require_operands(paths)
    flags = {option for option, _ in options}
    touch_paths(state, paths, flags)


WRITE_COMMANDS = {
    "chown": command_chown,
    "touch": command_touch,
}


# Original module: main
# Эмулятор командной оболочки UNIX-подобной ОС.

import argparse
import getpass
import os
import socket
import sys


DEFAULT_USER = "user"
HOME_MARK = "~"
PATH_SEPARATOR = "/"
PROMPT_END = "$ "
EXIT_COMMAND = "exit"
EXIT_SUCCESS = 0
EXIT_FAILURE = 1
SCRIPT_ENCODING = "utf-8"
COMMANDS = {**READ_COMMANDS, **WRITE_COMMANDS}


def create_argument_parser():
    # Создаёт парсер параметров командной строки.
    parser = argparse.ArgumentParser(
        description="UNIX-like shell emulator"
    )
    parser.add_argument(
        "--vfs-path",
        required=True,
        help="path to the physical VFS location",
    )
    parser.add_argument(
        "--prompt",
        help="custom input prompt",
    )
    parser.add_argument(
        "--script",
        help="path to the startup script",
    )
    return parser


def parse_arguments(arguments=None):
    # Разбирает параметры командной строки.
    return create_argument_parser().parse_args(arguments)


def print_configuration(config):
    # Выводит заданные параметры для отладки.
    print("Configuration:")
    print(f"  VFS path: {config.vfs_path}")
    print(f"  Prompt: {config.prompt}")
    print(f"  Startup script: {config.script}")


def get_username():
    # Возвращает имя текущего пользователя реальной ОС.
    # 
    #     Если определить имя не удалось, возвращает DEFAULT_USER.
    #     
    try:
        return getpass.getuser()
    except (KeyError, OSError, ImportError):
        return DEFAULT_USER


def get_hostname():
    # Возвращает имя компьютера, на котором запущен эмулятор.
    return socket.gethostname()


def get_current_dir():
    # Возвращает текущий каталог для приглашения.
    # 
    #     Домашний каталог заменяется на «~», разделители пути приводятся
    #     к виду UNIX («/»).
    #     
    cwd = os.getcwd()
    home = os.path.expanduser(HOME_MARK)
    if cwd == home:
        return HOME_MARK
    if cwd.startswith(home + os.sep):
        cwd = HOME_MARK + cwd[len(home):]
    return cwd.replace(os.sep, PATH_SEPARATOR)


def get_prompt(custom_prompt=None, state=None):
    # Возвращает пользовательское или стандартное приглашение.
    if custom_prompt is not None:
        return custom_prompt
    user = get_username()
    host = get_hostname()
    directory = state.cwd if state is not None else get_current_dir()
    return f"{user}@{host}:{directory}{PROMPT_END}"


def parse_command(line):
    # Разделяет введённую строку на команду и список аргументов.
    # 
    #     Разделителем служат пробельные символы. Для пустой строки
    #     возвращает пустое имя команды и пустой список аргументов.
    #     
    parts = line.split()
    if not parts:
        return "", []
    return parts[0], parts[1:]


def execute_command(name, args, state):
    # Выполняет команду; ошибки сообщаются, exit завершает сеанс.
    try:
        if name == EXIT_COMMAND:
            require_no_arguments(args)
            return False
        handler = COMMANDS.get(name)
        if handler is None:
            raise CommandError("command not found")
        handler(state, args)
    except CommandError as error:
        print(f"{name}: {error}")
    return True


def execute_line(line, state):
    # Разбирает и выполняет одну строку команды.
    name, args = parse_command(line)
    if not name:
        return True
    return execute_command(name, args, state)


def run_startup_script(script_path, state, custom_prompt=None):
    # Выполняет сценарий в общем состоянии оболочки, пропуская ошибки.
    try:
        with open(script_path, encoding=SCRIPT_ENCODING) as script:
            for raw_line in script:
                line = raw_line.rstrip("\r\n")
                print(f"{get_prompt(custom_prompt, state)}{line}")
                if not execute_line(line, state):
                    return False
    except (OSError, UnicodeError) as error:
        print(f"Startup script error: {error}")
    return True


def run_repl(state, custom_prompt=None):
    # Запускает REPL: Ctrl+D завершает работу, Ctrl+C сбрасывает ввод.
    while True:
        try:
            line = input(get_prompt(custom_prompt, state))
        except EOFError:
            print()
            break
        except KeyboardInterrupt:
            print()
            continue
        if not execute_line(line, state):
            break


def main(arguments=None):
    # Читает настройки, выполняет скрипт и запускает REPL.
    config = parse_arguments(arguments)
    print_configuration(config)
    try:
        vfs_root = load_vfs(config.vfs_path)
    except VFSError as error:
        print(f"VFS error: {error}")
        return EXIT_FAILURE
    directories, files = count_nodes(vfs_root)
    print(f"VFS loaded: {directories} directories, {files} files")
    state = ShellState(vfs_root)
    if config.script is not None:
        should_continue = run_startup_script(
            config.script, state, config.prompt
        )
        if not should_continue:
            return EXIT_SUCCESS
    run_repl(state, config.prompt)
    return EXIT_SUCCESS



def BAD_head(TextData, LineCount, NormalizeCRLF, SkipEmpty, TrimLines, AddNumbers, UpperCase, PrefixText):
    # Ordinary comment in place of a docstring: process the first requested LF lines.
    if LineCount < 0:
        raise ValueError("negative line count")
    if LineCount == 0:
        return ""
    if TextData == "":
        return ""
    if NormalizeCRLF:
        TextData = TextData.replace("\r\n", "\n")
    Lines = TextData.split("\n")
    HasFinalLF = TextData.endswith("\n")
    if HasFinalLF:
        Lines.pop()
    if LineCount == 10:
        LineCount = min(10, len(Lines))
    Result = []
    Used = 0
    Position = 0
    while Position < len(Lines):
        if Used >= LineCount:
            break
        CurrentLine = Lines[Position]
        Position += 1
        if SkipEmpty:
            if CurrentLine == "":
                continue
        if TrimLines:
            CurrentLine = CurrentLine.strip(" \t\r")
        if UpperCase:
            CurrentLine = CurrentLine.upper()
        if AddNumbers:
            CurrentLine = str(Used + 1) + ":" + CurrentLine
        if PrefixText != "":
            CurrentLine = PrefixText + CurrentLine
        Result.append(CurrentLine)
        Used += 1
    if len(Result) == 0:
        return ""
    Answer = "\n".join(Result)
    if HasFinalLF:
        Answer += "\n"
    elif Position < len(Lines):
        Answer += "\n"
    return Answer


def first_lines(text, count):
    # Actual head command uses this implementation, optionally in another language.
    import subprocess
    from pathlib import Path
    backend = os.environ.get("SHELL_HEAD_BACKEND", "python")
    if backend == "python":
        return BAD_head(text, count, False, False, False, False, False, "")
    base = Path(__file__).resolve().parent
    native_suffix = ".exe" if os.name == "nt" else ""
    programs = {
        "javascript": ["node", str(base / "bad_head.js")],
        "java": ["java", "-cp", str(base / "build"), "bad_shell"],
        "go": [str(base / "build" / ("bad_go" + native_suffix))],
        "csharp": ["mono", str(base / "build" / "bad_cs.exe")],
        "kotlin": ["java", "-jar", str(base / "build" / "bad_kotlin.jar")],
        "rust": [str(base / "build" / ("bad_rust" + native_suffix))],
    }
    if backend not in programs:
        raise CommandError("unknown head backend: " + backend)
    try:
        result = subprocess.run(programs[backend] + [str(min(count, text.count("\n") + 1))], input=text.encode("utf-8"), capture_output=True, timeout=20)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise CommandError("head backend unavailable: " + str(error)) from error
    if result.returncode:
        raise CommandError("head backend failed: " + result.stderr.decode("utf-8", errors="replace").strip())
    return result.stdout.decode("utf-8")

import unittest
shell = sys.modules[__name__]

# Inline regression module: test_main.py
# Тесты эмулятора командной оболочки.

import io
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock


VFS_PATH = str(Path(__file__).resolve().parent / "vfs" / "minimal.xml")


def call_and_capture(func, *args):
    # Вызывает func и возвращает пару (результат, вывод в stdout).
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        result = func(*args)
    return result, buffer.getvalue()


class ParseCommandTests(unittest.TestCase):
    # Проверка разбора строки на команду и аргументы.

    def test_command_without_arguments(self):
        # Команда без аргументов.
        self.assertEqual(shell.parse_command("ls"), ("ls", []))

    def test_command_with_arguments(self):
        # Команда с несколькими аргументами.
        self.assertEqual(
            shell.parse_command("ls -l /tmp"), ("ls", ["-l", "/tmp"])
        )

    def test_extra_whitespace(self):
        # Лишние пробелы и табуляция не влияют на результат.
        self.assertEqual(
            shell.parse_command("  cd \t  docs  "), ("cd", ["docs"])
        )

    def test_empty_line(self):
        # Пустая строка и строка из пробелов дают пустую команду.
        self.assertEqual(shell.parse_command(""), ("", []))
        self.assertEqual(shell.parse_command("   "), ("", []))


class PromptTests(unittest.TestCase):
    # Проверка формирования приглашения к вводу.

    def test_prompt_format(self):
        # Приглашение имеет вид user@host:dir$ .
        with mock.patch.object(shell, "get_username", return_value="alice"):
            with mock.patch.object(shell, "get_hostname", return_value="pc"):
                with mock.patch.object(
                    shell, "get_current_dir", return_value="~/work"
                ):
                    self.assertEqual(shell.get_prompt(), "alice@pc:~/work$ ")

    def test_custom_prompt(self):
        # Пользовательское приглашение заменяет стандартное.
        self.assertEqual(shell.get_prompt("vfs> "), "vfs> ")

    def test_username_fallback(self):
        # Если имя пользователя не определить, берётся запасное значение.
        with mock.patch("getpass.getuser", side_effect=OSError):
            self.assertEqual(shell.get_username(), shell.DEFAULT_USER)

    def test_hostname_from_os(self):
        # Имя компьютера берётся из реальной ОС.
        with mock.patch("socket.gethostname", return_value="my-host"):
            self.assertEqual(shell.get_hostname(), "my-host")


class CurrentDirTests(unittest.TestCase):
    # Проверка отображения текущего каталога в приглашении.

    def setUp(self):
        # Задаёт условный домашний каталог.
        self.home = os.path.join(os.sep, "home", "alice")

    def check_dir(self, cwd, expected):
        # Проверяет результат get_current_dir для заданного cwd.
        with mock.patch("os.getcwd", return_value=cwd):
            with mock.patch("os.path.expanduser", return_value=self.home):
                self.assertEqual(shell.get_current_dir(), expected)

    def test_home_directory(self):
        # Домашний каталог отображается как ~.
        self.check_dir(self.home, "~")

    def test_inside_home(self):
        # Вложенный каталог отображается относительно ~.
        self.check_dir(os.path.join(self.home, "work"), "~/work")

    def test_outside_home(self):
        # Каталог вне домашнего отображается полным путём.
        self.check_dir(os.path.join(os.sep, "tmp"), "/tmp")


class ExecuteCommandTests(unittest.TestCase):
    # Проверка встроенных команд, ошибок и завершения сеанса.

    def setUp(self):
        # Загружает тестовую VFS.
        self.state = ShellState(load_vfs(VFS_PATH))

    def test_exit_stops_shell(self):
        # exit без аргументов завершает сеанс.
        result, output = call_and_capture(
            shell.execute_command, "exit", [], self.state
        )
        self.assertFalse(result)
        self.assertEqual(output, "")

    def test_ls_lists_vfs(self):
        # ls выводит содержимое виртуального каталога.
        result, output = call_and_capture(
            shell.execute_command, "ls", [], self.state
        )
        self.assertTrue(result)
        self.assertEqual(output, "hello.txt\n")

    def test_cd_changes_virtual_directory(self):
        # cd изменяет состояние VFS без смены реального каталога.
        self.state.root.children["docs"] = Directory("docs")
        cwd = os.getcwd()
        result, output = call_and_capture(
            shell.execute_command, "cd", ["docs"], self.state
        )
        self.assertTrue(result)
        self.assertEqual(output, "")
        self.assertEqual(self.state.cwd, "/docs")
        self.assertEqual(os.getcwd(), cwd)

    def test_unknown_command(self):
        # Неизвестная команда сообщает ошибку и продолжает сеанс.
        result, output = call_and_capture(
            shell.execute_command, "foo", ["bar"], self.state
        )
        self.assertTrue(result)
        self.assertEqual(output, "foo: command not found\n")


class ConfigurationTests(unittest.TestCase):
    # Проверка параметров командной строки и их вывода.

    def test_default_arguments(self):
        # Остальные параметры необязательны.
        config = shell.parse_arguments(["--vfs-path", VFS_PATH])
        self.assertEqual(config.vfs_path, VFS_PATH)
        self.assertIsNone(config.prompt)
        self.assertIsNone(config.script)

    def test_all_arguments(self):
        # Все поддерживаемые флаги сохраняют переданные значения.
        config = shell.parse_arguments(
            [
                "--vfs-path",
                "vfs.xml",
                "--prompt",
                "demo> ",
                "--script",
                "startup.txt",
            ]
        )
        self.assertEqual(config.vfs_path, "vfs.xml")
        self.assertEqual(config.prompt, "demo> ")
        self.assertEqual(config.script, "startup.txt")

    def test_configuration_output(self):
        # При запуске выводятся все три параметра.
        config = shell.parse_arguments(
            ["--vfs-path", "vfs.xml", "--prompt", "demo> "]
        )
        _, output = call_and_capture(shell.print_configuration, config)
        self.assertEqual(
            output,
            "Configuration:\n"
            "  VFS path: vfs.xml\n"
            "  Prompt: demo> \n"
            "  Startup script: None\n",
        )


class StartupScriptTests(unittest.TestCase):
    # Проверка последовательного выполнения стартового скрипта.

    def setUp(self):
        # Создаёт временный каталог для файлов сценариев.
        self.temp_dir = tempfile.TemporaryDirectory()
        self.state = ShellState(load_vfs(VFS_PATH))

    def tearDown(self):
        # Удаляет временные файлы сценариев.
        self.temp_dir.cleanup()

    def create_script(self, contents):
        # Создаёт стартовый скрипт с заданным содержимым.
        path = os.path.join(self.temp_dir.name, "startup.txt")
        with open(path, "w", encoding=shell.SCRIPT_ENCODING) as script:
            script.write(contents)
        return path

    def test_commands_and_errors_are_shown(self):
        # После ошибочной команды выполняются следующие строки.
        path = self.create_script("cat missing\nunknown\ncat hello.txt\n")
        result, output = call_and_capture(
            shell.run_startup_script, path, self.state, "demo> "
        )
        self.assertTrue(result)
        self.assertEqual(
            output,
            "demo> cat missing\n"
            "cat: missing: no such file or directory\n"
            "demo> unknown\n"
            "unknown: command not found\n"
            "demo> cat hello.txt\n"
            "Привет из VFS!",
        )

    def test_exit_stops_script(self):
        # Команда exit не позволяет выполнить оставшиеся строки.
        path = self.create_script("exit\nls ignored\n")
        result, output = call_and_capture(
            shell.run_startup_script, path, self.state, "demo> "
        )
        self.assertFalse(result)
        self.assertEqual(output, "demo> exit\n")

    def test_missing_script_reports_error(self):
        # Ошибка открытия сценария выводится, работа может продолжиться.
        path = os.path.join(self.temp_dir.name, "missing.txt")
        result, output = call_and_capture(
            shell.run_startup_script, path, self.state, "demo> "
        )
        self.assertTrue(result)
        self.assertIn("Startup script error:", output)
        self.assertIn("missing.txt", output)


class ReplTests(unittest.TestCase):
    # Проверка цикла чтения и выполнения команд.

    def run_with_input(self, inputs):
        # Запускает REPL с заданными вводами и возвращает вывод.
        with mock.patch("builtins.input", side_effect=inputs) as fake_input:
            state = ShellState(load_vfs(VFS_PATH))
            _, output = call_and_capture(shell.run_repl, state)
        self.fake_input = fake_input
        return output

    def test_commands_then_exit(self):
        # Команды выполняются по очереди, пустые строки пропускаются.
        output = self.run_with_input(["ls", "", "foo", "exit"])
        self.assertEqual(
            output,
            "hello.txt\nfoo: command not found\n",
        )

    def test_exit_stops_reading(self):
        # После exit ввод больше не читается.
        self.run_with_input(["exit", "ls"])
        self.assertEqual(self.fake_input.call_count, 1)

    def test_eof_stops_shell(self):
        # Конец ввода (Ctrl+D) завершает работу.
        output = self.run_with_input(EOFError)
        self.assertEqual(output, "\n")

    def test_keyboard_interrupt_continues(self):
        # Ctrl+C сбрасывает строку, но не завершает работу.
        output = self.run_with_input([KeyboardInterrupt, "exit"])
        self.assertEqual(output, "\n")
        self.assertEqual(self.fake_input.call_count, 2)

    def test_custom_prompt_is_used(self):
        # REPL передаёт input пользовательское приглашение.
        with mock.patch(
            "builtins.input", side_effect=["exit"]
        ) as fake_input:
            call_and_capture(
                shell.run_repl, ShellState(load_vfs(VFS_PATH)), "demo> "
            )
        fake_input.assert_called_once_with("demo> ")


class MainTests(unittest.TestCase):
    # Проверка точки входа.

    def test_missing_vfs_parameter(self):
        # Без обязательного пути argparse возвращает ошибку.
        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                shell.main([])
        self.assertEqual(error.exception.code, 2)

    def test_vfs_error_stops_before_script_and_repl(self):
        # Ошибка VFS предотвращает выполнение сценария и REPL.
        with mock.patch.object(shell, "run_startup_script") as script:
            with mock.patch.object(shell, "run_repl") as repl:
                result, output = call_and_capture(shell.main, [
                    "--vfs-path", VFS_PATH + ".missing",
                    "--script", "startup.txt"
                ])
        self.assertEqual(result, 1)
        self.assertIn("VFS error:", output)
        script.assert_not_called()
        repl.assert_not_called()

    def test_invalid_vfs_stops_before_repl(self):
        # Повреждённая VFS не запускает REPL.
        path = str(Path(VFS_PATH).with_name("invalid.xml"))
        with mock.patch.object(shell, "run_repl") as repl:
            result, output = call_and_capture(shell.main, ["--vfs-path", path])
        self.assertEqual(result, 1)
        self.assertIn("VFS error:", output)
        repl.assert_not_called()

    def test_vfs_is_loaded_before_startup_script(self):
        # VFS загружается до выполнения стартового сценария.
        with mock.patch.object(
            shell, "load_vfs", wraps=shell.load_vfs
        ) as loader:
            def run_script(*args):
                # Проверяет порядок вызова загрузчика и сценария.
                loader.assert_called_once_with(VFS_PATH)
                return False
            with mock.patch.object(
                shell, "run_startup_script", side_effect=run_script
            ):
                result, _ = call_and_capture(shell.main, [
                    "--vfs-path", VFS_PATH, "--script", "startup.txt"
                ])
        self.assertEqual(result, 0)

    def test_main_returns_success(self):
        # main возвращает код успешного завершения.
        with mock.patch("builtins.input", side_effect=["exit"]):
            result, _ = call_and_capture(shell.main, ["--vfs-path", VFS_PATH])
        self.assertEqual(result, shell.EXIT_SUCCESS)

    def test_main_runs_script_before_repl(self):
        # exit в стартовом сценарии завершает эмулятор до REPL.
        with tempfile.TemporaryDirectory() as temp_dir:
            path = os.path.join(temp_dir, "startup.txt")
            with open(
                path, "w", encoding=shell.SCRIPT_ENCODING
            ) as script:
                script.write("exit\n")
            arguments = [
                "--vfs-path",
                VFS_PATH,
                "--prompt",
                "demo> ",
                "--script",
                path,
            ]
            result, output = call_and_capture(shell.main, arguments)
        self.assertEqual(result, shell.EXIT_SUCCESS)
        self.assertIn(f"VFS path: {VFS_PATH}", output)
        self.assertIn("Prompt: demo> ", output)
        self.assertIn(f"Startup script: {path}", output)
        self.assertTrue(output.endswith("demo> exit\n"))




# Inline regression module: test_commands.py
# Проверки команд этапа 4, виртуальных путей и общего состояния сеанса.

import os
import tempfile
from pathlib import Path
import unittest
from unittest import mock



class CommandTests(unittest.TestCase):
    # Проверка наблюдаемого поведения встроенных команд.

    def setUp(self):
        # Создаёт VFS с вложенными, пустыми и двоичными файлами.
        lines = "".join(f"line {number}\n" for number in range(1, 13))
        leaf = Directory("leaf", {"text": File("text", b"last\n")})
        docs = Directory("docs", {"leaf": leaf})
        self.root = Directory("/", {
            "docs": docs,
            "empty": Directory("empty"),
            "alpha": File("alpha", b"first\nsecond\nthird"),
            "long": File("long", lines.encode()),
            "blank": File("blank", b""),
            "binary": File("binary", b"\xff\x00"),
            ".hidden": File(".hidden", b"secret"),
            "-file": File("-file", b"dash"),
        })
        self.state = ShellState(self.root)

    def run_line(self, line):
        # Выполняет команду и возвращает признак продолжения и вывод.
        return call_and_capture(shell.execute_line, line, self.state)

    def test_ls_default_and_hidden(self):
        # ls сортирует имена, а -a включает скрытые элементы.
        _, output = self.run_line("ls")
        self.assertEqual(output.splitlines(), [
            "-file", "alpha", "binary", "blank", "docs", "empty", "long"
        ])
        _, output = self.run_line("ls -a")
        self.assertIn(".hidden", output.splitlines())

    def test_ls_long_file_and_empty_directory(self):
        # Длинный вывод показывает тип и размер; пустой каталог допустим.
        _, output = self.run_line("ls -l alpha")
        fields = output.split()
        self.assertEqual(fields[0], "-")
        self.assertEqual(fields[3], "18")
        self.assertEqual(fields[-1], "alpha")
        _, output = self.run_line("ls empty")
        self.assertEqual(output, "")
        _, output = self.run_line("ls -al docs")
        fields = output.split()
        self.assertEqual(fields[0], "d")
        self.assertEqual(fields[3], "0")
        self.assertEqual(fields[-1], "leaf")

    def test_ls_multiple_paths_and_partial_error(self):
        # Ошибка одного пути не мешает перечислению остальных.
        _, output = self.run_line("ls missing docs")
        self.assertIn("docs:\nleaf\n", output)
        self.assertIn("no such file or directory", output)

    def test_cd_absolute_relative_parent_and_previous(self):
        # cd поддерживает абсолютные пути, ., .. и предыдущий каталог.
        host_cwd = os.getcwd()
        self.run_line("cd /docs/leaf")
        self.assertEqual(self.state.cwd, "/docs/leaf")
        self.run_line("cd ../.")
        self.assertEqual(self.state.cwd, "/docs")
        _, output = self.run_line("cd -")
        self.assertEqual(output, "/docs/leaf\n")
        self.run_line("cd")
        self.assertEqual(self.state.cwd, "/")
        self.assertEqual(os.getcwd(), host_cwd)

    def test_failed_cd_preserves_state(self):
        # Ошибочный переход не изменяет текущий и предыдущий каталоги.
        self.run_line("cd docs")
        before = self.state.cwd, self.state.previous_cwd
        for line in ("cd /missing", "cd /alpha", "cd docs empty", "cd -z"):
            with self.subTest(line=line):
                self.assertTrue(self.run_line(line)[0])
                self.assertEqual(
                    (self.state.cwd, self.state.previous_cwd), before
                )

    def test_path_components_and_root_boundary(self):
        # Повторные / и .. не позволяют покинуть виртуальный корень.
        path, node = resolve_path(self.state, "//docs///leaf/../../..")
        self.assertEqual(path, "/")
        self.assertIs(node, self.root)
        self.run_line("cd /docs")
        path, node = resolve_path(self.state, "leaf/./text")
        self.assertEqual(path, "/docs/leaf/text")
        self.assertEqual(node.data, b"last\n")

    def test_traversal_through_file_is_rejected(self):
        # file/.., file/. и завершающий / требуют настоящего каталога.
        for path in ("alpha/..", "alpha/.", "alpha/", "alpha/child"):
            with self.subTest(path=path):
                with self.assertRaisesRegex(CommandError, "not a directory"):
                    resolve_path(self.state, path)
        with self.assertRaises(CommandError):
            resolve_path(self.state, "")

    def test_cat_preserves_text_and_handles_multiple_files(self):
        # cat сохраняет переносы и не добавляет завершающую новую строку.
        _, output = self.run_line("cat alpha blank docs/leaf/text")
        self.assertEqual(output, "first\nsecond\nthirdlast\n")
        _, output = self.run_line("cat -- -file")
        self.assertEqual(output, "dash")

    def test_file_errors_do_not_stop_later_operands(self):
        # После ошибки файла обрабатывается следующий файловый операнд.
        _, output = self.run_line("cat missing docs/leaf/text")
        self.assertIn("last\n", output)
        self.assertIn("no such file or directory", output)
        for path in ("docs", "binary"):
            with self.subTest(path=path):
                with self.assertRaises(CommandError):
                    read_text(self.state, path)

    def test_head_default_custom_zero_and_multiple(self):
        # head поддерживает 10 строк, -n, --lines, ноль и несколько файлов.
        _, output = self.run_line("head long")
        self.assertEqual(len(output.splitlines()), 10)
        self.assertTrue(output.endswith("line 10\n"))
        _, output = self.run_line("head -n 2 alpha")
        self.assertEqual(output, "first\nsecond\n")
        _, output = self.run_line("head --lines=1 alpha docs/leaf/text")
        self.assertEqual(
            output,
            "==> alpha <==\nfirst\n==> docs/leaf/text <==\nlast\n",
        )
        _, output = self.run_line("head -n 0 alpha")
        self.assertEqual(output, "")

    def test_invalid_arguments_report_errors_and_continue(self):
        # Ошибки опций и операндов сообщаются без завершения сеанса.
        lines = (
            "ls -z", "cat", "cat -z alpha", "head", "head -n",
            "head -n bad alpha", "head -n -1 alpha", "head -z alpha",
            "uptime x", "exit x",
        )
        for line in lines:
            with self.subTest(line=line):
                result, output = self.run_line(line)
                self.assertTrue(result)
                self.assertTrue(output.startswith(line.split()[0] + ":"))
        self.assertEqual(self.run_line("cat docs/leaf/text")[1], "last\n")

    def test_uptime_is_elapsed_emulated_time(self):
        # uptime использует монотонное время с запуска эмулируемой ОС.
        self.state.started = 100.0
        with mock.patch("emulator.time.monotonic", return_value=3761.0):
            _, output = self.run_line("uptime")
        self.assertEqual(output, "up 01:01:01\n")

    def test_prompt_uses_virtual_directory_and_os_identity(self):
        # Приглашение обновляет виртуальный путь после cd.
        self.run_line("cd docs")
        with mock.patch.object(shell, "get_username", return_value="alice"):
            with mock.patch.object(shell, "get_hostname", return_value="pc"):
                prompt = shell.get_prompt(state=self.state)
        self.assertEqual(prompt, "alice@pc:/docs$ ")
        self.assertEqual(shell.get_prompt("fixed> ", self.state), "fixed> ")


class IntegrationTests(unittest.TestCase):
    # Проверка общего состояния сценария и REPL и сохранности XML.

    def test_script_state_reaches_repl_and_source_is_unchanged(self):
        # REPL продолжает сценарий в том же каталоге без записи в XML.
        source = Path(__file__).resolve().parent / "vfs/demo.xml"
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            vfs = folder / "vfs.xml"
            vfs.write_bytes(source.read_bytes())
            script = folder / "startup.txt"
            script.write_text(
                "cd /documents/study/practice\ncat missing\n", encoding="utf-8"
            )
            before = vfs.read_bytes()
            with mock.patch("builtins.input", side_effect=["cat task.txt",
                                                         "exit"]) as reader:
                code, output = call_and_capture(shell.main, [
                    "--vfs-path", str(vfs), "--script", str(script)
                ])
            self.assertEqual(code, 0)
            self.assertIn("Вариант 13\n", output)
            self.assertIn("no such file or directory", output)
            self.assertTrue(
                reader.call_args_list[0].args[0].endswith(
                    ":/documents/study/practice$ "
                )
            )
            self.assertEqual(vfs.read_bytes(), before)
            self.assertEqual(set(folder.iterdir()), {vfs, script})

    def test_head_preserves_non_lf_characters(self):
        # head не считает CR и вертикальную табуляцию отдельными строками.
        root = Directory("/", {"text": File("text", b"a\rb\vc\nd\n")})
        _, output = call_and_capture(
            shell.execute_line, "head -n 1 text", ShellState(root)
        )
        self.assertEqual(output, "a\rb\vc\n")




# Inline regression module: test_mutations.py
# Проверки chown, touch, временных меток и сохранности источника VFS.

import tempfile
import unittest
from pathlib import Path
from unittest import mock


TEST_TIME = 1234567890.0


class MutationTests(unittest.TestCase):
    # Изменения виртуальных файлов и каталогов без операций над ОС.

    def setUp(self):
        # Создаёт каталог и файл с фиксированным содержимым и метками.
        self.file = File("text", b"original", owner="alice", group="staff",
                         accessed=1.0, modified=2.0)
        self.docs = Directory("docs", {"text": self.file}, owner="alice")
        self.state = ShellState(Directory("/", {"docs": self.docs}))

    def run_line(self, line):
        # Выполняет строку и перехватывает вывод команд.
        return call_and_capture(shell.execute_line, line, self.state)

    def test_chown_owner_and_group(self):
        # chown меняет владельца и группу, не меняя данные и метки.
        self.run_line("chown bob docs/text")
        self.assertEqual(self.file.owner, "bob")
        self.assertEqual(self.file.group, "staff")
        self.run_line("chown carol:students docs/text")
        self.assertEqual((self.file.owner, self.file.group),
                         ("carol", "students"))
        self.assertEqual(self.file.data, b"original")
        self.assertEqual((self.file.accessed, self.file.modified), (1.0, 2.0))

    def test_chown_directories_root_and_multiple_operands(self):
        # chown обрабатывает каталоги, корень и несколько путей.
        self.run_line("chown 1000:2000 / docs docs/text")
        for node in (self.state.root, self.docs, self.file):
            self.assertEqual((node.owner, node.group), ("1000", "2000"))
        _, output = self.run_line("ls -l docs/text")
        self.assertIn("1000 2000", output)

    def test_chown_directory_is_not_recursive(self):
        # Изменение владельца каталога не меняет его дочерние файлы.
        self.run_line("chown bob docs")
        self.assertEqual(self.docs.owner, "bob")
        self.assertEqual(self.file.owner, "alice")

    def test_chown_errors_do_not_stop_later_paths(self):
        # Ошибка одного пути не мешает изменению остальных операндов.
        result, output = self.run_line("chown bob missing docs/text")
        self.assertTrue(result)
        self.assertIn("no such file or directory", output)
        self.assertEqual(self.file.owner, "bob")

    def test_touch_creates_empty_files_and_updates_existing(self):
        # touch создаёт пустой файл и сохраняет содержимое существующего.
        with mock.patch("emulator.time.time", return_value=TEST_TIME):
            self.run_line("touch new docs/text")
        node = self.state.root.children["new"]
        self.assertIsInstance(node, File)
        self.assertEqual(node.data, b"")
        self.assertEqual((node.accessed, node.modified), (TEST_TIME, TEST_TIME))
        self.assertEqual(self.file.data, b"original")
        self.assertEqual((self.file.accessed, self.file.modified),
                         (TEST_TIME, TEST_TIME))
        _, output = self.run_line("ls")
        self.assertIn("new", output.splitlines())

    def test_touch_access_and_modified_modes(self):
        # -a меняет только доступ, -m только модификацию, -am обе метки.
        with mock.patch("emulator.time.time", return_value=TEST_TIME):
            self.run_line("touch -a docs/text")
        self.assertEqual((self.file.accessed, self.file.modified),
                         (TEST_TIME, 2.0))
        self.file.accessed = 1.0
        with mock.patch("emulator.time.time", return_value=TEST_TIME):
            self.run_line("touch -m docs/text")
        self.assertEqual((self.file.accessed, self.file.modified),
                         (1.0, TEST_TIME))
        with mock.patch("emulator.time.time", return_value=TEST_TIME):
            self.run_line("touch -am docs/text")
        self.assertEqual((self.file.accessed, self.file.modified),
                         (TEST_TIME, TEST_TIME))

    def test_touch_no_create_and_option_terminator(self):
        # -c не создаёт файл, -- позволяет использовать имя с дефисом.
        _, output = self.run_line("touch -c missing")
        self.assertEqual(output, "")
        self.assertNotIn("missing", self.state.root.children)
        with mock.patch("emulator.time.time", return_value=TEST_TIME):
            self.run_line("touch -c docs/text")
        self.assertEqual(self.file.modified, TEST_TIME)
        self.run_line("touch -- -file")
        self.run_line("chown bob -- -file")
        self.assertEqual(self.state.root.children["-file"].owner, "bob")

    def test_touch_relative_paths_and_directory_timestamps(self):
        # touch поддерживает относительные пути и метки каталогов.
        self.run_line("cd docs")
        with mock.patch("emulator.time.time", return_value=TEST_TIME):
            self.run_line("touch child . .. /docs/")
        self.assertEqual(self.docs.children["child"].data, b"")
        self.assertEqual(self.docs.modified, TEST_TIME)
        self.assertEqual(self.state.root.modified, TEST_TIME)

    def test_touch_errors_do_not_stop_later_operands(self):
        # touch не создаёт родительские каталоги и продолжает после ошибки.
        result, output = self.run_line("touch missing/child docs/text/child ok")
        self.assertTrue(result)
        self.assertIn("no such file or directory", output)
        self.assertIn("not a directory", output)
        self.assertIn("ok", self.state.root.children)
        self.assertNotIn("missing", self.state.root.children)

    def test_invalid_arguments_preserve_file(self):
        # Ошибочные владельцы и опции не меняют существующий файл.
        lines = (
            "chown", "chown bob", "chown bad:name:group docs/text",
            "chown :staff docs/text", "chown bob: docs/text",
            "chown -R bob docs/text", "touch", "touch -z docs/text",
            "touch docs/text/", "touch docs/text/..",
        )
        for line in lines:
            with self.subTest(line=line):
                result, output = self.run_line(line)
                self.assertTrue(result)
                self.assertTrue(output.startswith(line.split()[0] + ":"))
                self.assertEqual(self.file.owner, "alice")
                self.assertEqual(self.file.data, b"original")
                self.assertEqual(self.file.modified, 2.0)


class PersistenceTests(unittest.TestCase):
    # Проверяет отсутствие записи в источник и сброс после перезапуска.

    def test_mutations_live_only_in_memory(self):
        # Файлы и владельцы изменяются в памяти, исходный XML не меняется.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vfs.xml"
            source = b'<vfs><file name="hello">Hello</file></vfs>'
            path.write_bytes(source)
            state = ShellState(load_vfs(path))
            call_and_capture(shell.execute_line, "touch new hello", state)
            call_and_capture(shell.execute_line, "chown bob hello new", state)
            self.assertEqual(state.root.children["hello"].owner, "bob")
            self.assertIn("new", state.root.children)
            self.assertEqual(path.read_bytes(), source)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            reloaded = load_vfs(path)
            self.assertNotIn("new", reloaded.children)
            with mock.patch("emulator.getpass.getuser", return_value="alice"):
                self.assertEqual(load_vfs(path).children["hello"].owner,
                                 "alice")
            path.unlink()
            call_and_capture(shell.execute_line, "touch after_delete", state)
            self.assertIn("after_delete", state.root.children)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_startup_mutations_are_visible_in_repl(self):
        # Изменения сценария видны интерактивным командам этого же сеанса.
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            vfs = folder / "vfs.xml"
            source = b'<vfs><directory name="docs"/></vfs>'
            vfs.write_bytes(source)
            script = folder / "startup.txt"
            script.write_text(
                "cd docs\ntouch new\nchown bob new\n", encoding="utf-8"
            )
            with mock.patch("builtins.input", side_effect=["ls -l", "exit"]):
                code, output = call_and_capture(shell.main, [
                    "--vfs-path", str(vfs), "--script", str(script)
                ])
            self.assertEqual(code, 0)
            self.assertIn("bob users 0", output)
            self.assertTrue(output.endswith(" new\n"))
            self.assertEqual(vfs.read_bytes(), source)
            self.assertEqual(set(folder.iterdir()), {vfs, script})

    def test_default_owner_fallback(self):
        # Начальный владелец получает запасное имя при ошибке ОС.
        with mock.patch("emulator.getpass.getuser", side_effect=OSError):
            self.assertEqual(File("x", b"").owner, "user")




# Inline regression module: test_vfs.py
# Проверки XML, структуры папок, текста и двоичных данных.
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parent


class VFSTests(unittest.TestCase):
    def test_minimal(self):
        # Минимальный источник содержит один текстовый файл.
        root = load_vfs(ROOT / "vfs/minimal.xml")
        self.assertIsInstance(root, Directory)
        self.assertEqual(root.name, "/")
        file = root.children["hello.txt"]
        self.assertIsInstance(file, File)
        self.assertEqual(file.data.decode("utf-8"), "Привет из VFS!")
        self.assertEqual(count_nodes(root), (0, 1))

    def test_multiple_files_and_binary(self):
        # Загрузчик сохраняет текст, пустой файл и двоичные байты.
        root = load_vfs(ROOT / "vfs/files.xml")
        self.assertEqual(count_nodes(root), (0, 4))
        self.assertEqual(root.children["data.bin"].data, bytes([0, 1, 2, 255]))
        self.assertEqual(root.children["empty.txt"].data, b"")
        self.assertEqual(root.children["notes.txt"].data.decode("utf-8"),
                         "Первая строка\nВторая строка\nТретья строка")

    def test_three_nested_directories(self):
        # Загрузчик сохраняет три уровня вложенных каталогов.
        root = load_vfs(ROOT / "vfs/nested.xml")
        study = root.children["documents"].children["study"]
        file = study.children["practice"].children["task.txt"]
        self.assertEqual(file.data.decode("utf-8"), "Вариант 13")
        self.assertEqual(count_nodes(root), (3, 2))

    def test_source_is_unchanged_and_nodes_live_in_memory(self):
        # Изменения в памяти не затрагивают XML и другие файлы.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vfs.xml"
            source = b'<vfs><file name="hello.txt">Hello</file></vfs>'
            path.write_bytes(source)
            root = load_vfs(path)
            root.children["hello.txt"].data = b"Changed in memory"
            self.assertEqual(path.read_bytes(), source)
            self.assertEqual(list(Path(directory).iterdir()), [path])
            path.unlink()
            self.assertEqual(
                root.children["hello.txt"].data, b"Changed in memory"
            )

    def test_missing_file(self):
        # Отсутствующий источник вызывает VFSError.
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaises(VFSError):
                load_vfs(Path(directory) / "missing.xml")

    def test_invalid_formats(self):
        # Неверная структура XML и base64 вызывают VFSError.
        examples = [
            '<vfs>', '<root/>', '<vfs><unknown/></vfs>',
            '<vfs><file/></vfs>', '<vfs><directory name="../docs"/></vfs>',
            '<vfs><file name="x"/><directory name="x"/></vfs>',
            '<vfs><file name="x" encoding="hex">00</file></vfs>',
            '<vfs><file name="x" encoding="base64">!!!</file></vfs>',
            '<vfs><file name="x"><file name="y"/></file></vfs>',
            '<vfs>unexpected text</vfs>',
            '<vfs extra="x"/>', '<vfs><file name="."/></vfs>',
            '<vfs><file name=".."/></vfs>',
            '<vfs><file name="x" extra="y"/></vfs>',
            '<vfs><directory name="x" encoding="text"/></vfs>',
            '<vfs><file name="x"/>unexpected tail</vfs>',
            '<vfs><directory name="x">unexpected text</directory></vfs>',
            '<vfs><file name="x" encoding="base64">Я</file></vfs>',
        ]
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vfs.xml"
            for example in examples:
                with self.subTest(xml=example):
                    path.write_text(example, encoding="utf-8")
                    with self.assertRaises(VFSError):
                        load_vfs(path)

    def test_empty_root_and_base64_whitespace(self):
        # Пустой корень и переносы строк base64 допустимы.
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vfs.xml"
            path.write_text('<vfs/>', encoding="utf-8")
            self.assertEqual(count_nodes(load_vfs(path)), (0, 0))
            path.write_text(
                '<vfs><file name="x" encoding="base64">'
                ' AAEC\n/w== </file></vfs>', encoding="utf-8"
            )
            self.assertEqual(
                load_vfs(path).children["x"].data, bytes([0, 1, 2, 255])
            )




if __name__ == "__main__":
    sys.exit(main())
