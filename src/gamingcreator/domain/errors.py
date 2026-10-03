from enum import IntEnum


class ExitCode(IntEnum):
    SUCCESS = 0
    INPUT = 2
    ENVIRONMENT = 3
    PROVIDER = 4
    STORAGE = 5
    BENCHMARK = 6
    BUDGET = 7
    CANCELLED = 130


class AppError(Exception):
    """A safe diagnostic constructed by the application, never from raw input."""

    def __init__(self, code: str, message: str, exit_code: ExitCode) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.exit_code = exit_code


def invalid_video() -> AppError:
    return AppError("input.video", "视频必须是可读取的非空本地文件。", ExitCode.INPUT)


def invalid_config() -> AppError:
    return AppError(
        "configuration.invalid", "配置文件无效，请检查版本与允许字段。", ExitCode.ENVIRONMENT
    )
