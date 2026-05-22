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
    if not os.path.exists("llama.cpp/build/bin/llama-completion"):
        raise FileNotFoundError("llama.cpp binary not found.")
```

## **GEN-002: Multi-Model llama.cpp Runtime**
Use subprocess to execute llama.cpp binaries with model paths.

```python
import subprocess

def run_llama_model(model_path, prompt, mmproj_path=None):
    cmd = [
        "./llama.cpp/build/bin/llama-completion",
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
Execute Ministral-3B with mmproj for multimodal support.

```python
def execute_ministral(prompt, mmproj_path):
    return run_llama_model(
        model_path="models/ministral-3b-instruct.gguf",
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
        model_path="models/devstral-24b.gguf",
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
        response = route_model(user_input)
        display_console_output(response)
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
Parse and emit response blocks.

```python
def emit_response(text, channel="console"):
    return f"""~walbert_response_start~
{text}
~walbert_response_end~
~walbert_response_channel_start~
{channel}
~walbert_response_channel_end~
"""

def parse_response(response_text):
    import re
    response_match = re.search(r"~walbert_response_start~\n(.*?)\n~walbert_response_end~", response_text, re.DOTALL)
    channel_match = re.search(r"~walbert_response_channel_start~\n(.*?)\n~walbert_response_channel_end~", response_text, re.DOTALL)
    return {
        "response": response_match.group(1).strip() if response_match else "",
        "channel": channel_match.group(1).strip() if channel_match else ""
    }
```

---

# **7. Scripts & Environment Implementation**

## **ENV-004: Config System**
Define paths in a config file.

```python
import json

def load_config():
    with open("config.json", "r") as f:
        return json.load(f)

def validate_config(config):
    required_keys = ["model_paths", "llama_binary_path"]
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
```

---

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

