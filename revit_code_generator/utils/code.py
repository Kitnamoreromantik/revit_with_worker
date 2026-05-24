import re
import asyncio
import ast
import json
import textwrap
import tempfile
import os

def clean_raw_json_from_llm(text: str):
    """Parse LLM pseudo-JSON or Python dict into a dict."""
    text = text.strip()

    # Remove markdown fences and other wrappers
    text = re.sub(r"^```(?:json)?", "", text)
    text = re.sub(r"```$", "", text).strip()

    # Try JSON first (strict)
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    # Try JSON5 if installed (tolerant JSON)
    try:
        import json5
        return json5.loads(text)
    except Exception:
        pass

    # Fallback: demjson3 (very tolerant)
    try:
        import demjson3
        return demjson3.decode(text)
    except Exception:
        pass

    # Last resort: literal_eval (Python dict)
    try:
        return ast.literal_eval(text)
    except Exception:
        pass

    return {}

def extract_code_and_explanation(text: str) -> tuple[str, str]:
    """Split LLM output into code and explanation using regex and heuristics."""

    # Heuristic 1: fenced code blocks
    match = re.search(r"```(?:\w+)?\s*(.*?)```", text, flags=re.DOTALL)
    if match:
        code = match.group(1).strip()
        full_block = match.group(0)  # includes backticks and language tag
        explanation = text.replace(full_block, "").strip()
        return code, explanation

    # # Heuristic 2: plausible Cypher-like lines
    # lines = text.strip().splitlines()
    # cypher_lines = [line for line in lines if line.strip().lower().startswith((
    #     "match", "create", "merge", "return", "with", "call"))]

    # if cypher_lines:
    #     start = lines.index(cypher_lines[0])
    #     code = "\n".join(lines[start:])
    #     explanation = "\n".join(lines[:start])
    #     return code.strip(), explanation.strip()

    # Fallback
    return text.strip(), ""


async def try_invoke_with_retries(model, payload, max_retries=3, delay=1.0):
    """
    Attempts to invoke an asynchronous LLM model multiple times, retrying on errors or None responses.

    Args:
        model: The model object with an asynchronous `ainvoke(payload)` method.
        payload: The input payload to send to the model.
        max_retries (int, optional): Maximum number of attempts before giving up. Default is 3.
        delay (float, optional): Delay in seconds between retries. Default is 0.5.

    Returns:
        The result of `model.ainvoke(payload)` if successful, otherwise None after all retries fail.

    Behavior:
        - Retries when `model.ainvoke(payload)` raises an exception or returns None.
        - Waits `delay` seconds between retries.
        - Logs retry attempts and failures to stdout.
    """
    for attempt in range(max_retries):
        try:
            result = await model.ainvoke(payload)
            if result is not None:
                return result
            else:
                print(f"Attempt {attempt + 1}: LLM returned None. Retrying...")
        except Exception as e:
            print(f"Attempt {attempt + 1}: Exception occurred: {e}. Retrying...")

        if attempt < max_retries - 1:
            await asyncio.sleep(delay)

    print(f"All {max_retries} attempts of LLM invocation has failed or returned None.")
    return None


def parse_llm_structured_output(output: str) -> dict | None:
    """
    Clean and safely parse structured JSON output from an LLM.

    Args:
        output (str): Raw JSON-like string from LLM.

    Returns:
        dict | None: Parsed dictionary with keys `node_labels` and `node_property_values`,
        or None if parsing/validation fails.
    """
    cleaned = (
        output
        .removeprefix("```json")
        .removesuffix("```")
        .replace("\n", "")
        .replace("\r", "")
        .replace("\\", "")
        .strip()
    )
    

    # cleaned_json = cleaned.replace("(", "[").replace(")", "]").replace("None", "null")
    cleaned_json = cleaned.replace("None", "null")

    try:
        parsed = json.loads(cleaned_json)
        # if not isinstance(parsed, dict):
        #     return None
        # if "node_labels" not in parsed and "node_property_values" not in parsed:
        #     return None
        return parsed
    except json.JSONDecodeError:
        return None


def clean_llm_code(code: str) -> str:
    return (
        code.replace("\\n", " ")
            .replace("\n", " ")
            .replace("\\t", " ")
            .replace("\t", " ")
            .replace("\\\"", "\"")
            .replace("\\\\", "\\")
            .strip()
    )

def wrap_cypher_query(query: str, width: int = 80) -> str:
    # Insert line breaks before common keywords
    keywords = ["MATCH", "WHERE", "RETURN", "WITH", "CREATE", "MERGE", "ORDER BY"]
    for kw in keywords:
        query = re.sub(rf"\b{kw}\b", f"\n{kw}", query, flags=re.IGNORECASE)

    # Ensure no line exceeds width
    return "\n".join(textwrap.fill(line, width=width) for line in query.splitlines())

def wrap_csharp_code(code: str, width: int = 100, indent_size: int = 4) -> str:
    """Normalize generated C# without changing tokens inside strings."""
    return code.replace("\r\n", "\n").replace("\r", "\n").strip()


import textwrap

def wrap_text(text: str, width: int = 50) -> str:
    """Wrap long text to a fixed width for readability."""
    if not isinstance(text, str):
        return text
    return "\n".join(textwrap.wrap(text, width))

def format_csharp_code(code: str) -> str:
    """Format a C# code string using clang-format with proper indentation."""
    if not isinstance(code, str) or not code.strip():
        return code

    # Create a temporary .cs file for clang-format
    with tempfile.NamedTemporaryFile(suffix=".cs", mode="w+", encoding="utf-8", delete=False) as tmp:
        tmp.write(code)
        tmp_path = tmp.name

    # Run clang-format in place
    # subprocess.run(["clang-format", "-i", tmp_path], check=False)

    # Read the formatted result back
    with open(tmp_path, encoding="utf-8") as f:
        formatted = f.read()

    os.remove(tmp_path)
    return formatted.strip()
