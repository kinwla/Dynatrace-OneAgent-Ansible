import base64
from pathlib import Path

from command.command_result import CommandResult
from command.command_wrapper import CommandWrapper
from command.windows.windows_command_executor import WindowsCommandExecutor
from typing_extensions import override


class WindowsCommandWrapper(CommandWrapper):
    def __init__(self, user: str, password: str):
        self.executor: WindowsCommandExecutor = WindowsCommandExecutor(user, password)

    @override
    def get_file_content(self, address: str, file: Path) -> CommandResult:
        return self.executor.execute(address, "type", str(file))

    def _run_powershell(self, address: str, script: str) -> CommandResult:
        # Encoding the script avoids quoting issues when passing it through cmd
        encoded = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
        return self.executor.execute(
            address, "powershell.exe", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded
        )

    @staticmethod
    def _quote(value: object) -> str:
        return "'" + str(value).replace("'", "''") + "'"

    @override
    def file_exists(self, address: str, file: Path) -> CommandResult:
        # Unlike cmd's "if exist", Test-Path resolves wildcards in any path component
        return self._run_powershell(address, f"if (Test-Path -Path {self._quote(file)}) {{ exit 0 }} else {{ exit 1 }}")

    def write_file(self, address: str, file: Path, content: str) -> CommandResult:
        return self._run_powershell(
            address, f"Set-Content -LiteralPath {self._quote(file)} -Value {self._quote(content)} -NoNewline"
        )

    def remove_items(self, address: str, pattern: Path) -> CommandResult:
        return self._run_powershell(
            address, f"Remove-Item -Path {self._quote(pattern)} -Recurse -Force -ErrorAction SilentlyContinue; exit 0"
        )

    @override
    def directory_exists(self, address: str, directory: Path) -> CommandResult:
        return self.executor.execute(address, f'if exist "{directory}\\*" (exit 0) else (exit 1)')

    def _run_directory_creation_command(self, address: str, directory: Path) -> CommandResult:
        result = CommandResult(0, "", "")
        if self.directory_exists(address, directory).returncode == 1:
            result = self.executor.execute(address, "md", str(directory))

        return result

    @override
    def create_directory(self, address: str, directory: Path) -> CommandResult:
        for parent in list(directory.parents)[::-1][1::]:
            result = self._run_directory_creation_command(address, parent)
            if result.returncode != 0:
                return result
        return self._run_directory_creation_command(address, directory)

    @override
    def run_command(self, address: str, command: str, *args: str) -> CommandResult:
        return self.executor.execute(address, f'"{command}"', *args)
