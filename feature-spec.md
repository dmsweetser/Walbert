# **Walbert — Feature Specification**

## **Version:** 2.1
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
  All I/O layers must be enabled, disabled, or set to require user authorization.

- **GEN-008: Console I/O Layer**
  The system must accept text input and display text output via the console.

- **GEN-009: Zero-State Boot**
  Walbert must operate with an empty database and learn its identity over time.

- **GEN-010: Conversation Reset**
  Walbert must autonomously determine when a conversation is complete.

- **GEN-011: Dual Conversation Logging**
  All conversations must be logged to both the database and raw log files.

- **GEN-012: Comprehensive Testing Framework**
  The system must include unit tests and integration tests for all components.

- **GEN-013: Factory Pattern Implementation**
  All major components must be instantiatable through factory methods.

- **GEN-014: llama.cpp Binary Path Configuration**
  The system must define and validate paths to llama.cpp compiled binaries.

---

# **2. AI / Model Features (AI)**

- **AI-001: Primary Model — Ministral-3B-Instruct-GGUF**
  Used for all default reasoning and decision-making via llama.cpp.

- **AI-002: llama.cpp Binary Execution**
  All model inference must be performed using llama.cpp compiled binaries.

- **AI-003: Smarter Cousin — Devstral-24B (Local)**
  Used only when the primary model decides it needs deeper reasoning.

- **AI-004: Autonomous Model Router**
  The primary model must autonomously decide when to:
  - Query its datastore via SQL
  - Execute stored skills
  - Perform multi-step reasoning

- **AI-005: System Prompt Awareness**
  Models must understand the DB schema, tag system, and response protocol.

- **AI-006: SQL Command Emission**
  Models must request DB reads/writes via structured SQL commands.

---

# **3. Unified I/O Layer Features (IOL)**

- **IOL-001: I/O Layer Configuration**
  The system must allow users to configure I/O layers via `io_config.json`.

- **IOL-002: User Authorization for Execution**
  Each I/O layer must support a user authorization step if configured.

- **IOL-003: Console I/O Layer**
  The system must accept text input and display text output via the console.

- **IOL-004: Python Code Execution Layer**
  The system must support executing Python code with user authorization.

- **IOL-005: Serial I/O Layer**
  The system must support bidirectional serial communication.

- **IOL-006: Bluetooth I/O Layer**
  The system must support Bluetooth device communication.

- **IOL-007: USB I/O Layer**
  The system must support USB device detection and communication.

---

# **4. Data & Storage Features (DATA)**

- **DATA-001: Items Table**
  Must store text, skills, and arbitrary content with generalized tags.

- **DATA-002: Tags Table**
  Must store unique tag names.

- **DATA-003: Item-Tags Mapping**
  Must support many-to-many relationships between items and tags.

- **DATA-004: Conversations Table**
  Must store summarized conversation sessions.

- **DATA-005: Messages Table**
  Must store individual messages with metadata.

- **DATA-006: Raw Conversation Logs**
  Must log all conversations to file in raw format.

---

# **5. Skill System Features (SKILL)**

- **SKILL-001: Skill Storage**
  Skills must be stored as items in the database with `type='skill'`.

- **SKILL-002: Skill Execution**
  Skills must run in isolated subprocesses with access to provided arguments.

- **SKILL-003: Skill Discovery**
  Skills must be discoverable using SQL queries against the items table.

- **SKILL-004: Self-Expansion**
  Walbert must be able to generate and store new skills using SQL commands.

---

# **6. Unified Walbert Response Format (MOD)**

Walbert must emit **all responses and internal deliberations** using the following block-based format.

## **6.1 Core Response Blocks**
```
~walbert_response_start~
<What it decided to say or do>

~walbert_response_channel_start~
<Where it will send the response (e.g., "console", "serial")>
```

## **6.2 Decision Blocks**
```
~walbert_should_query_datastore_start~
YES/NO

~walbert_conversation_complete_start~
YES/NO
```

## **6.3 Action Blocks**
```
~walbert_sql_execute_start~
SQL_STATEMENT

~walbert_skill_execute_start~
SKILL_NAME
```

## **6.4 Rules**
- All text must appear within walbert_ blocks.
- Walbert may execute multiple internal rounds before replying to the user.
- Walbert must autonomously determine when a conversation is complete.

---

# **7. Scripts & Environment Features (ENV)**

- **ENV-001: install.sh**
  Must create venv, install minimal dependencies, and validate llama.cpp binary paths.

- **ENV-002: run.sh**
  Must activate venv, validate llama.cpp binaries, and start the console interface.

- **ENV-003: requirements.txt**
  Must list only essential Python packages.

- **ENV-004: Config System**
  Must define paths to all GGUF models and llama.cpp compiled binaries.

---

# **8. Testing Features (TEST)**

- **TEST-001: Unit Test Coverage**
  All major components must have comprehensive unit tests.

- **TEST-002: Integration Tests**
  System integration must be verified with integration tests.

- **TEST-003: Mocking Infrastructure**
  All external dependencies must be mockable for testing.

---

# **9. SOLID Principles Features (SOLID)**

- **SOLID-001: Single Responsibility Principle**
  Each class must have only one reason to change.

- **SOLID-002: Open/Closed Principle**
  The system must be open for extension but closed for modification.

- **SOLID-003: Dependency Inversion Principle**
  High-level modules must not depend on low-level modules.

- **SOLID-004: Factory Pattern**
  The system must implement factory patterns for creating complex objects.
