# danielou-ai 🚀

An autonomous, **100% local and private agentic AI assistant** designed specifically for **Embedded Software Engineering** and hardware-software integration. 

This repository is a customized and optimized fork of `ultraworkers/claw-code`, officially rebranded as `danielou-ai`. It runs completely offline on your local machine using **Ollama** as the inference engine, making it fully compliant with professional NDA requirements for proprietary hardware development.

---

## 🌟 Core Pillars & Sprint Goals

### 1. Rebranded & Native Windows GNU Build (Axe 1)
*   The Rust workspace compiles natively into a standalone binary named `danielou.exe` using the MinGW/MSYS2 toolchain (`x86_64-pc-windows-gnu`).
*   Bypasses heavy MSVC Visual Studio requirements and handles Windows native Schannel TLS (`native-tls`) and syntax highlighting (`syntect` via pure-Rust `fancy-regex`) without complex external C linkages.
*   Fully integrated globally in Windows `PATH` (via Scoop shims).

### 2. Datasheet Parser & Hardware RAG (Axe 2)
*   **Location:** [`src/parse_datasheet.py`](./src/parse_datasheet.py)
*   Extracts register lists, offsets, bitfields, access types, and descriptions from semiconductor PDF Reference Manuals (STM32, ESP32, etc.) using `pdfplumber`.
*   Preserves tabular structures and hexadecimal addresses (`0x4000_0000`) by converting them into structured JSON register maps, ready to be indexed by the agent's local SQLite RAG database.

### 3. ARM Cortex-M HardFault Decoder (Axe 3)
*   **Location:** [`src/decode_hardfault.py`](./src/decode_hardfault.py)
*   Decodes low-level CPU registry crash dumps when debugging STM32 or other Cortex-M systems.
*   Parses **CFSR** (Configurable Fault Status Register: MMFSR, BFSR, UFSR) and **HFSR** (HardFault Status Register) to pinpoint precise crash causes (e.g., Null pointer dereferencing, division by zero, unaligned access, or invalid state).
*   Validates memory addresses in **BFAR** and **MMFAR**.

### 4. Bare-Metal Embedded C Code Generator (Axe 4)
*   **Location:** [`src/generate_embedded_c.py`](./src/generate_embedded_c.py)
*   Generates MISRA-C compliant register structure definitions and driver files from the parsed JSON register maps.
*   **Zero Dynamic Allocation:** Optimized for constrained bare-metal targets.
*   **Padding Aligned:** Automatically inserts `RESERVED` padding fields into structs to guarantee alignment with hardware memory offsets.
*   Generates static inline helper functions for bitmask manipulation.

---

## 🛠️ Repository Architecture

*   **`rust/`**: Canonical Rust workspace containing the `danielou` CLI agent core.
*   **`src/`**: Companion Python toolkit containing hardware analysis scripts (`parse_datasheet.py`, `decode_hardfault.py`, `generate_embedded_c.py`).
*   **`scratch/`**: Safe local folder containing test files and mock register configurations (e.g., [`usart_test.json`](./scratch/usart_test.json)).

---

## 🚀 Quick Start (Windows PowerShell)

### 1. Prerequisites
Ensure you have **Ollama** installed on your system. If not, install it using Scoop:
```powershell
scoop install ollama
```

### 2. Configure Local Inference
Save the `OLLAMA_HOST` variable permanently to route all model queries through your local Ollama server:
```powershell
[Environment]::SetEnvironmentVariable("OLLAMA_HOST", "http://127.0.0.1:11434", "User")
```

Download a powerful local code model (reopening your terminal first):
```powershell
# Recommended for standard GPUs/VRAM (7B parameters)
ollama run qwen2.5-coder:7b

# Recommended for CPU-only or integrated graphics (1.5B parameters)
ollama run qwen2.5-coder:1.5b
```

### 3. Run the Agent Globally
The compiled binary has been shimmed under Scoop. Simply run it from any folder:
```powershell
# Check version and latest Git SHA
danielou --version

# Run diagnostic tool
danielou doctor

# Start the interactive agent chat
danielou
```

---

## 💡 Usage Examples

### Parse a PDF Datasheet
```bash
python src/parse_datasheet.py path/to/stm32_usart.pdf -s 120 -e 125 -o scratch/usart.json
```

### Generate C Header from JSON Map
```bash
python src/generate_embedded_c.py scratch/usart.json USART1 -o scratch/usart1_regs.h
```

### Decode a CPU HardFault
```bash
python src/decode_hardfault.py --cfsr 0x00010000 --hfsr 0x40000000
```
*Output:*
```text
====================================================
        ARM CORTEX-M HARDFAULT CRASH DECODER        
====================================================
CFSR  : 0x00010000
HFSR  : 0x40000000
----------------------------------------------------
[*] HFSR Details:
  [FORCED] Forced HardFault: Fault escalated because handler was disabled or blocked.

[*] Usage Faults (UFSR):
  [UNDEFINSTR] Undefined instruction: CPU tried to execute an unknown instruction.
====================================================
```

---

## 🔒 Security & Safety
Because `danielou` runs with full terminal access, it operates under an explicit **Workspace-Write Permission Mode**. The agent will always prompt you for authorization before executing shell commands (`bash` tool) or editing critical files. You remain in complete control of your workspace.
