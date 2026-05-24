import json
import sys
from dataclasses import asdict, is_dataclass
from datetime import datetime
from pathlib import Path
from langchain_core.messages import BaseMessage
from loguru import logger
from rich.console import Console
from rich.text import Text

console = Console()


class Tee:
    def __init__(self, *streams):
        self.streams = streams
    def write(self, data):
        for s in self.streams: 
            s.write(data)
            s.flush()
    def flush(self):
        for s in self.streams: 
            s.flush()


# def configure_printing_to_cli_and_file(log_dir: str = "logs") -> None:
#     """
#     Configures the CLI output use Rich for better formatting in the console.
#     """
#     timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M")
#     log_path = f"{log_dir}/run_{timestamp}.txt"

#     txt_file = open(log_path, "w", encoding="utf-8")
#     sys.stdout = Tee(sys.__stdout__, txt_file)
#     console = Console()

#     return console

def configure_printing_to_cli_and_file(log_dir: str = "logs") -> Console:
    """
    Configures the CLI output using Rich for nice formatting,
    and duplicates everything printed to console into a .txt log file.
    """
    Path(log_dir).mkdir(exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_path = f"{log_dir}/run_{timestamp}.txt"

    txt_file = open(log_path, "w", encoding="utf-8")

    # Capture BOTH stdout and stderr
    sys.stdout = Tee(sys.__stdout__, txt_file)
    sys.stderr = Tee(sys.__stderr__, txt_file)

    console = Console()
    return console


def configure_logger(log_dir: str = "logs", trace_states: bool = True) -> None:
    """
    Configure Loguru with optional suppression of 'state'-tagged messages.
    """
    Path(log_dir).mkdir(exist_ok=True)
    logger.remove()
    timestamp = datetime.now().strftime("%Y-%m-%d_%H:%M")
    log_path = f"{log_dir}/run_{timestamp}.log"

    # Console output (only errors)
    logger.add(
        sys.stderr,
        format="{level} | {name}:{function}():{line} | {message}",
        level="ERROR",
        colorize=True,
        backtrace=True,
        diagnose=True,
    )

    # File output (optionally filter state logs)
    logger.add(
        log_path,
        format="{message}",
        level="INFO",
        encoding="utf-8",
        colorize=False,
        enqueue=True,
        filter=None if trace_states else lambda r: r["extra"].get("tag") != "state",
    )

    # Redirect unhandled exceptions to Loguru
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("Unhandled exception")

    sys.excepthook = handle_exception

    return logger



def serialize_message(msg: BaseMessage) -> dict:
    """Format LangChain messages for better readability in logs."""
    return {
        "type": msg.type,
        "content": msg.content,
        "metadata": getattr(msg, "response_metadata", {}),
        "kwargs": getattr(msg, "additional_kwargs", {}),
    }


def recursive_serialize(obj):
    """Recursively serialize LangChain messages or state."""
    if isinstance(obj, BaseMessage):
        return serialize_message(obj)
    elif is_dataclass(obj):
        return {k: recursive_serialize(v) for k, v in asdict(obj).items()}
    elif isinstance(obj, dict):
        return {k: recursive_serialize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [recursive_serialize(i) for i in obj]
    else:
        return obj


def dump_pretty_json(obj) -> str:
    """Convert object to readable JSON string."""
    return json.dumps(recursive_serialize(obj), indent=4, ensure_ascii=False)


def log_banner(text: str, width: int=50, fill: str="="):
    line = fill * width
    message_line = f"\n{text} ".center(width, ' ')
    banner = f"\n{line}{message_line}\n{line}"
    logger.info("{}", banner)


def print_new_question(content: str):
    msg = Text(f" NEW QUESTION: {content} ", style="bold white on red")
    print("\n")
    console.rule(msg, style="red")  # draws a red horizontal line with the text centered
    print("\n")
