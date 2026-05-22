# **Walbert — Feature Specification**

## **Version:** 1.8
## **Author:** Daniel
## **Purpose:** Define the complete feature set for the Walbert local agent system, explicitly built on llama.cpp compiled binaries.

---

# **1. General System Features (GEN)**

- **GEN-001: Local-Only Execution**
  Walbert must run entirely on Linux using only local llama.cpp compiled binaries.

- **GEN-002: Multi-Model llama.cpp Runtime**
  Walbert must load and manage multiple GGUF models simultaneously (Ministral-3B, mmproj, Devstral-24B) via llama.cpp binaries.
  The mmproj is passed as a parameter to the llama.cpp binary during Ministral-3B execution.

- **GEN-003: Minimal Dependency Footprint**
  The system must rely only on Python and llama.cpp compiled binaries.

- **GEN-004: Virtual Environment Setup**
  Installation must create a Python venv and install only essential packages.

- **GEN-005: SQLite Datastore**
  A single SQLite database must store all items, tags, skills, conversations, and memories.

- **GEN-006: Tag-Based Retrieval**
  All stored content must be retrievable by one or more tags (generalized as categories).

- **GEN-007: Unified Walbert Response Protocol**
  All model outputs must use a simplified block-based format for responses and internal deliberation.

- **GEN-008: Console I/O Layer**
  All external communication must occur via a console interface.

- **GEN-009: Zero-State Boot**
  Walbert must operate with an empty database and learn its identity and skills over time.

- **GEN-010: Conversation Reset**
  Walbert must autonomously determine when a conversation is complete and reset its state.

- **GEN-011: Dual Conversation Logging**
  All conversations must be logged to both the database (summary and full form) and a raw log file.

- **GEN-012: Comprehensive Testing Framework**
  The system must include unit tests, integration tests, and mocking infrastructure for all major components.

- **GEN-013: Factory Pattern Implementation**
  All major components must be instantiatable through factory methods for dependency injection and testability.

- **GEN-014: llama.cpp Binary Path Configuration**
  The system must define and validate paths to llama.cpp compiled binaries (e.g., `llama-completion`).

- **GEN-015: Console Input/Output**
  The system must accept text input and display text output via the console.

---

# **2. AI / Model Features (AI)**

- **AI-001: Primary Model — Ministral-3B-Instruct-2512-GGUF**
  Used for all default reasoning and decision-making via llama.cpp binary.
  The MMPROJ is passed as a parameter to enable multimodal processing.

- **AI-002: llama.cpp Binary Execution**
  All model inference must be performed using llama.cpp compiled binaries with subprocess execution.

- **AI-003: Smarter Cousin — Devstral-24B (Local)**
  Used only when the primary model decides it needs deeper reasoning or coding assistance via llama.cpp binary.

- **AI-004: Autonomous Model Router**
  The primary model must autonomously decide when to:
  - Query its datastore
  - Invoke a stored skill
  - Call Devstral-24B via llama.cpp binary
  - Perform multi-step reasoning

  **The user never selects Devstral directly.**

- **AI-005: System Prompt Awareness**
  Models must understand the DB schema, tag system, skill system, and response protocol.

- **AI-006: DB Command Emission**
  Models must be able to request DB reads/writes via structured commands.

- **AI-007: Skill Creation Commands**
  Models must be able to define new skills by emitting structured commands.

- **AI-008: Skill Execution Commands**
  Models must be able to request execution of stored skills with arguments.

---

# **3. Console I/O Layer Features (IOL)**

- **IOL-001: Console Input**
  The system must accept text input from the console.

- **IOL-002: Console Output**
  The system must display text output to the console.

- **IOL-003: Input Types**
  Supported input types:
  - Text

- **IOL-004: Output Types**
  Supported output types:
  - Text
  - Skill-generated artifacts

---

# **4. Data & Storage Features (DATA)**

- **DATA-001: Items Table**
  Must store text, skills, and arbitrary content with generalized tags.

- **DATA-002: Tags Table**
  Must store unique tag names (generalized as categories).

- **DATA-003: Item-Tags Mapping**
  Must support many-to-many relationships between items and tags.

- **DATA-004: Conversations Table**
  Must store summarized conversation sessions and full conversation data.

- **DATA-005: Messages Table**
  Must store individual messages with metadata (queryable by tag/category).

- **DATA-006: Memory Storage**
  Must support storing and retrieving persistent memories with tiered relevance.

- **DATA-007: Raw Conversation Logs**
  Must log all conversations to file in raw format, separate from the database.

---

# **5. Skill System Features (SKILL)**

- **SKILL-001: Skill Schema**
  Skills must be stored as items containing code, metadata, and tags.

- **SKILL-002: Skill Execution Sandbox**
  Skills must run in isolated subprocesses.

- **SKILL-003: Hardware Interaction Potential**
  Skills must be able to interact with USB or serial devices.

- **SKILL-004: Self-Expansion**
  Walbert must be able to generate new skills to extend its own capabilities.

- **SKILL-005: Skill Discovery**
  Skills must be discoverable by tag or name.

---

# **6. Unified Walbert Response Format (MOD)**

Walbert must emit **all responses and internal deliberations** using the following block-based format.

## **6.1 walbert_response Block**
```
~walbert_response_start~
<What it decided to say or do>
~walbert_response_end~
```

## **6.2 walbert_response_channel Block**
```
~walbert_response_channel_start~
<Where it will send the response (e.g., "console", "internal")>
~walbert_response_channel_end~
```

## **6.3 Rules**
- All text must appear within walbert_ blocks.
- Walbert may execute multiple internal rounds before replying to the user.
- Walbert must autonomously determine when a conversation is complete and reset its state.

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

- **ENV-005: llama.cpp Binary Validation**
  The system must validate the existence of llama.cpp binaries at startup.

---

# **8. Identity & Behavior Features (ID)**

- **ID-001: Agent Memory**
  Walbert must store and recall data with a tiered approach to avoid context bloat.

- **ID-002: System Prompt Personality**
  Must define behavior, protocol, and DB/IOL awareness.

- **ID-003: Emergent Capability Growth**
  Walbert must grow capabilities by generating new skills and memories.

- **ID-004: Single-Prompt Operation**
  Walbert must be optimized to handle one user prompt at a time, resetting after completion.

---

# **9. Hardware & Peripheral Features (HW)**

- **HW-001: USB Device Detection**
  Walbert must detect and identify USB devices connected to the host system.

- **HW-002: Serial Communication**
  Walbert must support bidirectional serial communication with connected devices.

- **HW-003: Bluetooth Device Pairing**
  Walbert must discover, pair, and communicate with Bluetooth devices.

- **HW-004: Device Firmware Generation**
  Walbert must generate and upload firmware (e.g., Arduino scripts) to compatible microcontrollers.

- **HW-005: Peripheral Integration**
  Walbert must integrate peripheral devices into its decision-making and response loops.

- **HW-006: Autonomous Hardware Interaction**
  Walbert must autonomously decide when and how to interact with connected hardware.

# **10. Autonomous Execution Features (AUTO)**

- **AUTO-001: Autonomous Decision-Making**
  Walbert must autonomously evaluate and execute actions without explicit user input.

- **AUTO-002: Self-Triggered Actions**
  Walbert must initiate actions based on internal state, datastore queries, or external events.

- **AUTO-003: Continuous Operation**
  Walbert must support long-running autonomous operation with periodic state resets.

- **AUTO-004: Event-Driven Execution**
  Walbert must respond to external events (e.g., hardware signals, timers) autonomously.

- **AUTO-005: Unified Channel Routing**
  Walbert must use `walbert_response_channel` blocks to determine the appropriate channel for each action or response.

- **AUTO-006: Cross-Channel Workflows**
  Walbert must support workflows that span multiple channels (e.g., receive input via console, interact with Bluetooth device, return response via console).

# **11. Testing Features (TEST)**

- **TEST-001: Unit Test Coverage**
  All major components must have comprehensive unit tests.

- **TEST-002: Integration Tests**
  System integration must be verified with integration tests, including llama.cpp binary execution and hardware interactions.

- **TEST-003: Mocking Infrastructure**
  All external dependencies (including llama.cpp binaries and hardware peripherals) must be mockable for testing.

- **TEST-004: Factory Pattern**
  All components must be instantiatable through factory methods.
