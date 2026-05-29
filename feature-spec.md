# **Walbert — Feature Specification**

## **Version:** 4.0
## **Author:** Daniel
## **Purpose:** Define the complete feature set for the Walbert local agent system.

---

# **1. General System Features (GEN)**

- **GEN-001: Local-Only Execution**
  Walbert must run entirely on Linux using only local llama.cpp compiled binaries.

- **GEN-002: Multi-Model llama.cpp Runtime**
  Walbert must load and manage multiple GGUF models via llama.cpp.

- **GEN-003: Minimal Dependency Footprint**
  The system must rely only on Python and llama.cpp compiled binaries.

- **GEN-004: Virtual Environment Setup**
  Installation must create a Python venv and install only essential packages.

- **GEN-005: SQLite Datastore**
  A single SQLite database must store all items, tags, conversations, and memories.

- **GEN-006: Unified Walbert Response Protocol**
  All model outputs must use a simplified block-based format for responses.

- **GEN-007: Configurable I/O Layers**
  All I/O layers must be enabled or disabled

- **GEN-008: Console I/O Layer**
  The system must accept text input and display text output via the console.

- **GEN-009: Zero-State Boot**
  Walbert must operate with an empty database and learn its identity over time.

- **GEN-010: Conversation Reset**
  Walbert must autonomously determine when a conversation is complete.

- **GEN-011: Raw Conversation Logging**
  All input/output and raw LLM output must be logged to raw log files.

- **GEN-012: Comprehensive Testing Framework**
  The system must include unit tests and integration tests for all components.

- **GEN-013: Factory Pattern Implementation**
  All major components must be instantiatable through factory methods.

- **GEN-014: llama.cpp Binary Path Configuration**
  The system must define and validate paths to llama.cpp compiled binaries.

- **GEN-015: Skill Management System**
  Walbert must support dynamic skill execution and storage.

---

# **2. AI / Model Features (AI)**

- **AI-001: Primary Model — Devstral-24B-Instruct-GGUF**
  Used for all default reasoning and decision-making via llama.cpp.

- **AI-002: llama.cpp Binary Execution**
  All model inference must be performed using llama.cpp compiled binaries.

- **AI-003: Autonomous Model Routing**
  The primary model must autonomously decide when to query its datastore via SQL.

- **AI-005: System Prompt Awareness**
  Models must understand the DB schema, tag system, and response protocol.

- **AI-006: SQL Command Emission**
  Models must request DB reads/writes via structured SQL commands.

- **AI-007: Skill Execution Blocks**
  Models must emit skill execution blocks for dynamic capability extension.

---

# **3. Unified I/O Layer Features (IOL)**

- **IOL-001: I/O Layer Configuration**
  The system must allow users to configure I/O layers via `io_config.json`.

- **IOL-002: Console I/O Layer**
  The system must accept text input and display text output via the console.

- **IOL-003: Serial I/O Layer**
  The system must support bidirectional serial communication.

- **IOL-004: Bluetooth I/O Layer**
  The system must support Bluetooth device communication.

- **IOL-005: USB I/O Layer**
  The system must support USB device detection and communication.

---

# **4. Data & Storage Features (DATA)**

- **DATA-001: Items Table**
  Must provide a basic items table for initial storage.

- **DATA-002: Raw Conversation Logs**
  Must log all input/output and raw LLM output to file in raw format.

- **DATA-003: Full Database Autonomy**
  Walbert must have complete control over database schema and data persistence.

- **DATA-004: Minimal Initial Schema**
  The system must initialize with only an items table for basic storage.

- **DATA-005: Dynamic Schema Evolution**
  Walbert must be able to modify the database schema through SQL commands.

---

## **5. Unified Walbert Response Format (MOD)**

Walbert must emit **all responses and internal deliberations** using the following block-based format with `walbert_` prefix:

### **5.1 Core Blocks**
```
[walbert_sql_execute]
SQL_STATEMENT
[/walbert_sql_execute]

[walbert_python_requirements]
# Python requirements WITHOUT VERSION NUMBERS
# Example:
package1
package2
[/walbert_python_requirements]

[walbert_python_execute]
# Python code to execute
import os
print("Hello from Python!")
[/walbert_python_execute]

[walbert_conversation_complete]
YES/NO
[/walbert_conversation_complete]

[walbert_sql_result]
SQL_RESULT_CONTENT
[/walbert_sql_result]

[walbert_python_result]
PYTHON_RESULT_CONTENT
[/walbert_python_result]
```

### **5.2 I/O Channel Blocks**
For each enabled I/O channel (console, serial, etc.):
```
[walbert_%channel%_response]
RESPONSE_CONTENT
[/walbert_%channel%_response]
```

### **5.3 Input Context Block**
```
[walbert_input_channel]
CHANNEL_NAME
[/walbert_input_channel]
```

### **5.4 Rules**
- All content must be enclosed between matching `walbert_` start and end tags.
- Walbert may respond to the user immediately while continuing background tasks.
- Walbert must provide clear indication when background tasks are in progress.
- Walbert must autonomously determine when a conversation is complete.
- Walbert may emit response blocks at any time during processing.
- Walbert has **FULL AUTONOMY** over database schema and data persistence.
- **ALL** data storage and retrieval must be managed through SQL commands in `[walbert_sql_execute]` blocks.
- **ALL** Python code execution must be managed through `[walbert_python_execute]` blocks.
- **ALL** Python requirements must be specified in `[walbert_python_requirements]` blocks without version numbers.
- No hard-coded database operations are allowed - **ALL** persistence must be handled through the protocol.
- Walbert must manage **ALL** aspects of its database, including:
  - Schema design and evolution
  - Data storage and retrieval
  - Memory and knowledge management
- The system provides **ONLY** a basic `items` table to start with.
- Walbert must define and manage all additional tables and schema elements.
- Raw conversation logs are stored in files - **NOT** in the database.
- Walbert must use the database **ONLY** for structured data it chooses to persist.
- **NO** hard-coded assumptions about schema structure are allowed.
- Walbert must decide what data to persist and how to structure it.
- Control flow is **AUTOMATIC**:
  - If there are pending `[walbert_sql_execute]` or `[walbert_python_execute]` blocks, Walbert continues processing
  - If no pending blocks exist, control automatically returns to the user

---

# **6. Scripts & Environment Features (ENV)**

- **ENV-001: install.sh**
  Must create venv, install minimal dependencies, and validate llama.cpp binary paths.

- **ENV-002: run.sh**
  Must activate venv, validate llama.cpp binaries, and start the console interface.

- **ENV-003: requirements.txt**
  Must list only essential Python packages.

- **ENV-004: Config System**
  Must define paths to all GGUF models and llama.cpp compiled binaries.

---

# **7. Testing Features (TEST)**

- **TEST-001: Unit Test Coverage**
  All major components must have comprehensive unit tests.

- **TEST-002: Integration Tests**
  System integration must be verified with integration tests.

- **TEST-003: Mocking Infrastructure**
  All external dependencies must be mockable for testing.

---

# **8. SOLID Principles Features (SOLID)**

- **SOLID-001: Single Responsibility Principle**
  Each class must have only one reason to change.

- **SOLID-002: Open/Closed Principle**
  The system must be open for extension but closed for modification.

- **SOLID-003: Dependency Inversion Principle**
  High-level modules must not depend on low-level modules.

- **SOLID-004: Factory Pattern**
  The system must implement factory patterns for creating complex objects.
