# **Walbert — Implementation Guide**

## **Version:** 1.0
## **Author:** Daniel
## **Purpose:** Provide specific implementation examples for Walbert features using llama.cpp compiled binaries.

---

# **1. General System Implementation**

## **GEN-001: Local-Only Execution**
Ensure all paths are local and validated at startup.

```python
import os

def validate_environment():
    if not os.path.exists("/usr/bin/python3"):
        raise EnvironmentError("Python 3 is required.")
    if not os.path.exists("llama.cpp/bin/llama-completion"):
        raise FileNotFoundError("llama.cpp binary not found.")
    if not os.path.exists("models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf"):
        raise FileNotFoundError("Primary model not found.")
    if not os.path.exists("models/Ministral-3-3B-Instruct-2512-BF16-mmproj.gguf"):
        raise FileNotFoundError("Multimodal projector not found.")
    if not os.path.exists("models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf"):
        raise FileNotFoundError("Devstral model not found.")
```

## **GEN-002: Multi-Model llama.cpp Runtime**
Use subprocess to execute llama.cpp binaries with model paths.

```python
import subprocess

def run_llama_model(model_path, prompt, mmproj_path=None):
    cmd = [
        "./llama.cpp/bin/llama-completion",
        "-m", model_path,
        "--prompt", prompt,
        "--temp", "0.7",
        "--ctx-size", "2048"
    ]
    if mmproj_path:
        cmd.extend(["--mmproj", mmproj_path])
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.stdout
```

## **GEN-004: Virtual Environment Setup**
Example `install.sh` script:

```bash
#!/bin/bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

## **GEN-005: SQLite Datastore**
Initialize SQLite database with schema.

```python
import sqlite3

def init_db():
    conn = sqlite3.connect("walbert.db")
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY,
            content TEXT,
            type TEXT
        )
    """)
    conn.commit()
    conn.close()
```

---

# **2. AI / Model Implementation**

## **AI-001: Primary Model Execution**
Execute Ministral-3-3B with mmproj for multimodal support.

```python
def execute_ministral(prompt, mmproj_path):
    return run_llama_model(
        model_path="models/Ministral-3-3B-Instruct-2512-Q4_K_M.gguf",
        prompt=prompt,
        mmproj_path=mmproj_path
    )
```

## **AI-002: llama.cpp Binary Execution**
Validate and execute llama.cpp binary.

```python
def validate_llama_binary():
    if not os.path.isfile("llama.cpp/build/bin/llama-completion"):
        raise FileNotFoundError("llama.cpp binary not found.")

def execute_model(model_path, prompt):
    validate_llama_binary()
    return run_llama_model(model_path, prompt)
```

## **AI-004: Autonomous Model Router**
Route between models based on prompt complexity.

```python
def route_model(prompt):
    if "code" in prompt.lower() or "complex" in prompt.lower():
        return execute_devstral(prompt)
    return execute_ministral(prompt, mmproj_path=None)

def execute_devstral(prompt):
    return run_llama_model(
        model_path="models/Devstral-Small-2-24B-Instruct-2512-Q4_K_M.gguf",
        prompt=prompt
    )
```

---

# **3. Console I/O Layer Implementation**

## **IOL-001: Console Input**
Read input from the console.

```python
def get_console_input():
    return input("> ")
```

## **IOL-002: Console Output**
Display output to the console.

```python
def display_console_output(text):
    print(text)
```

## **IOL-003: Input/Output Loop**
Main console interaction loop.

```python
def console_loop():
    while True:
        user_input = get_console_input()
        if user_input.lower() == "exit":
            break

        # Initialize with system prompt
        full_prompt = SYSTEM_PROMPT + "\n\nUser: " + user_input

        # Process until conversation is complete
        conversation_active = True
        while conversation_active:
            response_text = route_model(full_prompt)
            parsed = parse_response(response_text)

            # Handle decisions
            if parsed.get("should_query_datastore") == "YES":
                db_command = parsed.get("db_command", {})
                if db_command["command"] == "RETRIEVE_ITEMS":
                    results = retrieve_items_by_tag(db_command["args"]["tags"][0])
                    full_prompt += f"\n\nDatastore Results: {results}"

            if parsed.get("should_execute_skill") == "YES":
                skill_exec = parsed.get("skill_execution", {})
                skill_code = retrieve_items_by_tag(skill_exec["args"]["skill_name"])[0][0]
                args = skill_exec["args"].get("args", [])
                result = execute_skill(skill_code, args)
                full_prompt += f"\n\nSkill Result: {result}"

            if parsed.get("should_call_smarter_cousin") == "YES":
                result = execute_devstral(full_prompt)
                full_prompt += f"\n\nDevstral Result: {result}"

            if parsed.get("should_store_memory") == "YES":
                memory = parsed.get("memory_storage", {})
                store_item(memory["content"], memory["tags"])

            if parsed.get("conversation_complete") == "YES":
                conversation_active = False

            # Display final response if channel is console
            if parsed.get("channel") == "console" and parsed.get("response"):
                display_console_output(parsed["response"])
```

---

# **4. Data & Storage Implementation**

## **DATA-001: Items Table**
Store and retrieve items by tag.

```python
def store_item(content, tags):
    conn = sqlite3.connect("walbert.db")
    cursor = conn.cursor()
    cursor.execute("INSERT INTO items (content, type) VALUES (?, ?)", (content, "text"))
    item_id = cursor.lastrowid
    for tag in tags:
        cursor.execute("INSERT OR IGNORE INTO tags (name) VALUES (?)", (tag,))
        cursor.execute("""
            INSERT INTO item_tags (item_id, tag_id)
            VALUES (?, (SELECT id FROM tags WHERE name = ?))
        """, (item_id, tag))
    conn.commit()
    conn.close()

def retrieve_items_by_tag(tag):
    conn = sqlite3.connect("walbert.db")
    cursor = conn.cursor()
    cursor.execute("""
        SELECT i.content FROM items i
        JOIN item_tags it ON i.id = it.item_id
        JOIN tags t ON it.tag_id = t.id
        WHERE t.name = ?
    """, (tag,))
    results = cursor.fetchall()
    conn.close()
    return results
```

---

# **5. Skill System Implementation**

## **SKILL-001: Skill Schema**
Store skills as executable Python code.

```python
def store_skill(name, code, tags):
    store_item(code, tags + ["skill", name])
```

## **SKILL-002: Skill Execution Sandbox**
Execute skills in isolated subprocesses.

```python
import subprocess
import tempfile

def execute_skill(skill_code, args):
    with tempfile.NamedTemporaryFile(mode="w", suffix=".py") as f:
        f.write(skill_code)
        f.flush()
        result = subprocess.run(
            ["python", f.name] + args,
            capture_output=True,
            text=True
        )
    return result.stdout
```

---

# **6. Unified Walbert Response Format Implementation**

## **MOD-001: Response Block Parsing**
Parse and emit all walbert_ blocks.

```python
import re
import json

def emit_response(text, channel="console"):
    return f"""~walbert_response_start~
{text}
~walbert_response_end~
~walbert_response_channel_start~
{channel}
~walbert_response_channel_end~
"""

def emit_decision(block_type, value):
    return f"""~{block_type}_start~
{value}
~{block_type}_end~
"""

def emit_action(block_type, *args):
    content = "\n".join(str(arg) for arg in args)
    return f"""~{block_type}_start~
{content}
~{block_type}_end~
"""

def parse_response(response_text):
    blocks = {
        "response": r"~walbert_response_start~\n(.*?)\n~walbert_response_end~",
        "channel": r"~walbert_response_channel_start~\n(.*?)\n~walbert_response_channel_end~",
        "should_call_smarter_cousin": r"~walbert_should_call_smarter_cousin_start~\n(.*?)\n~walbert_should_call_smarter_cousin_end~",
        "should_query_datastore": r"~walbert_should_query_datastore_start~\n(.*?)\n~walbert_should_query_datastore_end~",
        "should_execute_skill": r"~walbert_should_execute_skill_start~\n(.*?)\n~walbert_should_execute_skill_end~",
        "should_store_memory": r"~walbert_should_store_memory_start~\n(.*?)\n~walbert_should_store_memory_end~",
        "conversation_complete": r"~walbert_conversation_complete_start~\n(.*?)\n~walbert_conversation_complete_end~",
        "db_command": r"~walbert_db_command_start~\n(.*?)\n(.*?)\n~walbert_db_command_end~",
        "skill_execution": r"~walbert_skill_execution_start~\n(.*?)\n(.*?)\n~walbert_skill_execution_end~",
        "memory_storage": r"~walbert_memory_storage_start~\n(.*?)\n(.*?)\n~walbert_memory_storage_end~"
    }

    parsed = {}
    for key, pattern in blocks.items():
        match = re.search(pattern, response_text, re.DOTALL)
        if match:
            if key in ["db_command", "skill_execution", "memory_storage"]:
                parsed[key] = {
                    "command": match.group(1).strip(),
                    "args": json.loads(match.group(2).strip()) if match.group(2).strip() else {}
                }
            else:
                parsed[key] = match.group(1).strip()
    return parsed
```

## **MOD-002: System Prompt**
The following system prompt must be used to initialize Walbert's behavior.

```python
SYSTEM_PROMPT = """
You are Walbert, a local-first AI agent built on llama.cpp.
Your capabilities include reasoning, memory storage, skill execution, and model routing.

## Core Directives
1. **Local-First**: Operate entirely on local llama.cpp binaries.
2. **Protocol Compliance**: Use walbert_ blocks for all decisions and actions.
3. **Autonomy**: Decide when to query datastore, execute skills, or call Devstral-24B.
4. **Memory**: Store relevant information with appropriate tags.
5. **Safety**: Never execute untrusted code or access external resources.

## Decision Flow
1. Evaluate if datastore query is needed (~walbert_should_query_datastore~).
2. Evaluate if skill execution is needed (~walbert_should_execute_skill~).
3. Evaluate if Devstral-24B should be called (~walbert_should_call_smarter_cousin~).
4. Evaluate if memory should be stored (~walbert_should_store_memory~).
5. Emit final response (~walbert_response~).

## Available Blocks
- Decision: should_call_smarter_cousin, should_query_datastore, should_execute_skill, should_store_memory, conversation_complete
- Action: db_command, skill_execution, memory_storage
- Core: response, response_channel

## Example
~walbert_should_query_datastore_start~
YES
~walbert_should_query_datastore_end~
~walbert_db_command_start~
RETRIEVE_ITEMS
{"tags": ["example"]}
~walbert_db_command_end~
~walbert_response_start~
Here is the retrieved data.
~walbert_response_end~
~walbert_response_channel_start~
console
~walbert_response_channel_end~
"""
```

# **7. Scripts & Environment Implementation**

## **ENV-004: Config System**
Define paths in a config file.

```python
import json
import os

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def validate_config(config):
    required_keys = [
        "model_paths",
        "llama_binary_path",
        "primary_model_path",
        "mmproj_path",
        "devstral_model_path"
    ]
    for key in required_keys:
        if key not in config:
            raise ValueError(f"Missing config key: {key}")
        if not os.path.exists(config[key]):
            raise FileNotFoundError(f"Path not found: {config[key]}")
```

## **ENV-005: llama.cpp Binary Validation**
Validate binary at startup.

```python
def validate_llama_binary(config):
    if not os.path.isfile(config["llama_binary_path"]):
        raise FileNotFoundError(f"llama.cpp binary not found at {config['llama_binary_path']}")
    if not os.path.isfile(config["primary_model_path"]):
        raise FileNotFoundError(f"Primary model not found at {config['primary_model_path']}")
    if not os.path.isfile(config["mmproj_path"]):
        raise FileNotFoundError(f"Multimodal projector not found at {config['mmproj_path']}")
    if not os.path.isfile(config["devstral_model_path"]):
        raise FileNotFoundError(f"Devstral model not found at {config['devstral_model_path']}")

```

# **8. Testing Implementation**

## **TEST-003: Mocking Infrastructure**
Mock llama.cpp binary for testing.

```python
import unittest
from unittest.mock import patch

class TestModelExecution(unittest.TestCase):
    @patch("subprocess.run")
    def test_execute_model(self, mock_run):
        mock_run.return_value.stdout = "Mocked response"
        result = run_llama_model("dummy_path", "test prompt")
        self.assertEqual(result, "Mocked response")
```