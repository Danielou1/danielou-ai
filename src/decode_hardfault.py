#!/usr/bin/env python3
"""
ARM Cortex-M HardFault & System Fault Decoder.
Decodes registers: CFSR (Configurable Fault Status Register),
HFSR (HardFault Status Register), BFAR (BusFault Address Register),
and MMFAR (MemManage Fault Address Register) to pinpoint crash root causes.
"""

import sys
import argparse

def decode_cfsr(cfsr_val):
    """
    CFSR consists of:
    - MMFSR (bits 7:0): MemManage Fault Status Register
    - BFSR (bits 15:8): BusFault Status Register
    - UFSR (bits 31:16): UsageFault Status Register
    """
    report = []
    
    # 1. MemManage Fault Status Register (MMFSR)
    mmfsr = cfsr_val & 0xFF
    mmfsr_report = []
    if mmfsr & (1 << 0):
        mmfsr_report.append("[IACCVIOL] Instruction access violation: MPUs prevented fetching instruction.")
    if mmfsr & (1 << 1):
        mmfsr_report.append("[DACCVIOL] Data access violation: MPU violation on load/store (e.g. Null pointer access).")
    if mmfsr & (1 << 3):
        mmfsr_report.append("[MUNSTKERR] MemManage fault on unstacking from exception handler.")
    if mmfsr & (1 << 4):
        mmfsr_report.append("[MSTKERR] MemManage fault on stacking for exception handler.")
    if mmfsr & (1 << 5):
        mmfsr_report.append("[MLSPERR] MemManage fault during lazy state preservation of FPU registers.")
    mmfar_valid = bool(mmfsr & (1 << 7))
    
    # 2. BusFault Status Register (BFSR)
    bfsr = (cfsr_val >> 8) & 0xFF
    bfsr_report = []
    if bfsr & (1 << 0):
        bfsr_report.append("[IBUSERR] Instruction bus error: prefetch failed.")
    if bfsr & (1 << 1):
        bfsr_report.append("[PRECISERR] Precise data bus error: MPU/bus error on precise data load/store.")
    if bfsr & (1 << 2):
        bfsr_report.append("[IMPRECISERR] Imprecise data bus error: MPU/bus error on buffered write (delayed write).")
    if bfsr & (1 << 3):
        bfsr_report.append("[UNSTKERR] BusFault on unstacking from exception handler.")
    if bfsr & (1 << 4):
        bfsr_report.append("[STKERR] BusFault on stacking for exception handler.")
    if bfsr & (1 << 5):
        bfsr_report.append("[LSPERR] BusFault during lazy state preservation of FPU registers.")
    bfar_valid = bool(bfsr & (1 << 7))

    # 3. UsageFault Status Register (UFSR)
    ufsr = (cfsr_val >> 16) & 0xFFFF
    ufsr_report = []
    if ufsr & (1 << 0):
        ufsr_report.append("[UNDEFINSTR] Undefined instruction: CPU tried to execute an unknown instruction.")
    if ufsr & (1 << 1):
        ufsr_report.append("[INVSTATE] Invalid state: CPU tried to execute in ARM mode (Cortex-M only supports Thumb mode/EPSR.T=1).")
    if ufsr & (1 << 2):
        ufsr_report.append("[INVPC] Invalid PC load: invalid EXC_RETURN code or integrity check failure.")
    if ufsr & (1 << 3):
        ufsr_report.append("[NOCP] No coprocessor: executed coprocessor/FPU instruction when it was disabled.")
    if ufsr & (1 << 8):
        ufsr_report.append("[UNALIGNED] Unaligned memory access: CPU performed unaligned access with alignment check enabled.")
    if ufsr & (1 << 9):
        ufsr_report.append("[DIVBYZERO] Division by zero: CPU attempted to divide by zero.")

    return {
        "mmfsr": mmfsr,
        "mmfsr_report": mmfsr_report,
        "mmfar_valid": mmfar_valid,
        "bfsr": bfsr,
        "bfsr_report": bfsr_report,
        "bfar_valid": bfar_valid,
        "ufsr": ufsr,
        "ufsr_report": ufsr_report
    }

def decode_hfsr(hfsr_val):
    report = []
    if hfsr_val & (1 << 1):
        report.append("[VECTTBL] Vector table read fault: BusFault during vector table read on exception vectoring.")
    if hfsr_val & (1 << 30):
        report.append("[FORCED] Forced HardFault: Fault escalated from MemManage, BusFault, or UsageFault because handler was disabled or blocked.")
    if hfsr_val & (1 << 31):
        report.append("[DEBUGEVT] Debug event: HardFault triggered by debug event (breakpoints, watchpoints).")
    return report

import re
import os
import subprocess

def decode_exc_return(lr_val):
    """Decodes the EXC_RETURN value in the Link Register (LR) during an exception."""
    if (lr_val & 0xFFFFFF00) != 0xFFFFFF00:
        return None
        
    report = []
    fpu_active = (lr_val & (1 << 4)) == 0
    thread_mode = (lr_val & (1 << 3)) != 0
    use_psp = (lr_val & (1 << 2)) != 0
    non_secure = (lr_val & (1 << 0)) != 0
    
    report.append(f"EXC_RETURN Value: 0x{lr_val:08X}")
    report.append(f"  [Stack Frame] {'Extended (FPU registers stacked)' if fpu_active else 'Standard (No FPU registers stacked)'}")
    report.append(f"  [Return Mode] {'Thread Mode (Application)' if thread_mode else 'Handler Mode (Nested Exception)'}")
    report.append(f"  [Active Stack] {'Process Stack Pointer (PSP)' if use_psp else 'Main Stack Pointer (MSP)'}")
    report.append(f"  [Security State] {'Non-Secure' if non_secure else 'Secure (TrustZone)'}")
    
    return {
        "fpu_active": fpu_active,
        "thread_mode": thread_mode,
        "use_psp": use_psp,
        "report": report
    }

def parse_stack_dump(stack_str):
    """Parses a string of hex values representing the stacked registers on exception entry."""
    hex_values = re.findall(r'0x[0-9A-Fa-f]+|[0-9A-Fa-f]{8}', stack_str)
    if not hex_values:
        return None
        
    words = []
    for val in hex_values:
        try:
            if val.lower().startswith("0x"):
                words.append(int(val, 16))
            else:
                words.append(int(val, 16))
        except ValueError:
            continue
            
    if len(words) < 8:
        print(f"Warning: Stack dump contains only {len(words)} words. At least 8 words are needed to extract PC/LR.", file=sys.stderr)
        return None
        
    r0 = words[0]
    r1 = words[1]
    r2 = words[2]
    r3 = words[3]
    r12 = words[4]
    lr = words[5]
    pc = words[6]
    xpsr = words[7]
    
    report = [
        f"Stacked Registers (Standard Context Frame):",
        f"  R0   : 0x{r0:08X}",
        f"  R1   : 0x{r1:08X}",
        f"  R2   : 0x{r2:08X}",
        f"  R3   : 0x{r3:08X}",
        f"  R12  : 0x{r12:08X}",
        f"  LR   : 0x{lr:08X} (Return Link - caller function)",
        f"  PC   : 0x{pc:08X} (Program Counter - crash address)",
        f"  xPSR : 0x{xpsr:08X}"
    ]
    
    return {
        "r0": r0, "r1": r1, "r2": r2, "r3": r3, "r12": r12,
        "lr": lr, "pc": pc, "xpsr": xpsr,
        "report": report
    }

def resolve_symbol(address, elf_path, addr2line_tool="arm-none-eabi-addr2line"):
    """Runs addr2line to get the function name and file line of the given address."""
    if not os.path.exists(elf_path):
        return f"Error: ELF file not found at: {elf_path}"
        
    cmd = [addr2line_tool, "-e", elf_path, "-f", "-C", f"0x{address:08X}"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, check=True)
        lines = result.stdout.strip().split("\n")
        if len(lines) >= 2:
            func = lines[0]
            loc = lines[1]
            return f"  Function: {func}\n  Source  : {loc}"
        return f"  Address : 0x{address:08X}"
    except FileNotFoundError:
        return f"  Warning : '{addr2line_tool}' not found in system PATH. Cannot resolve symbols."
    except Exception as e:
        return f"  Error running addr2line: {e}"

def main():
    parser = argparse.ArgumentParser(description="ARM Cortex-M HardFault and System Control Block (SCB) Register Decoder.")
    parser.add_argument("--cfsr", help="Configurable Fault Status Register (CFSR) value in hex (e.g. 0x00010000)", default="0x0")
    parser.add_argument("--hfsr", help="HardFault Status Register (HFSR) value in hex (e.g. 0x40000000)", default="0x0")
    parser.add_argument("--bfar", help="BusFault Address Register (BFAR) value in hex", default="0x0")
    parser.add_argument("--mmfar", help="MemManage Fault Address Register (MMFAR) value in hex", default="0x0")
    parser.add_argument("--lr", "--exc-return", help="Link Register / EXC_RETURN value (e.g. 0xFFFFFFFD)", default=None)
    parser.add_argument("--stack", help="Stack dump as space-separated hex words (minimum 8 words)", default=None)
    parser.add_argument("--elf", help="Path to ELF binary for symbol resolution", default=None)
    parser.add_argument("--addr2line", help="Path to addr2line executable (default: arm-none-eabi-addr2line)", default="arm-none-eabi-addr2line")
    
    args = parser.parse_args()
    
    try:
        cfsr_val = int(args.cfsr, 16)
        hfsr_val = int(args.hfsr, 16)
        bfar_val = int(args.bfar, 16)
        mmfar_val = int(args.mmfar, 16)
        lr_val = int(args.lr, 16) if args.lr else None
    except ValueError as e:
        print(f"Error: Invalid hex values provided. {e}", file=sys.stderr)
        sys.exit(1)
        
    print("====================================================")
    print("        ARM CORTEX-M HARDFAULT CRASH DECODER        ")
    print("====================================================")
    print(f"CFSR  : 0x{cfsr_val:08X}")
    print(f"HFSR  : 0x{hfsr_val:08X}")
    print(f"BFAR  : 0x{bfar_val:08X}")
    print(f"MMFAR : 0x{mmfar_val:08X}")
    if lr_val:
        print(f"LR/EXC: 0x{lr_val:08X}")
    print("----------------------------------------------------")
    
    # 1. Decode EXC_RETURN
    if lr_val:
        exc_info = decode_exc_return(lr_val)
        if exc_info:
            print("[*] EXC_RETURN (LR) Details:")
            for line in exc_info["report"]:
                print(f"  {line}")
            print("----------------------------------------------------")
            
    # 2. Decode Stack Frame
    stacked_pc = None
    stacked_lr = None
    if args.stack:
        stack_info = parse_stack_dump(args.stack)
        if stack_info:
            print("[*] Stacked Register Frame:")
            for line in stack_info["report"]:
                print(f"  {line}")
            stacked_pc = stack_info["pc"]
            stacked_lr = stack_info["lr"]
            print("----------------------------------------------------")
            
    # 3. Resolve symbols if ELF is provided
    if args.elf and (stacked_pc or stacked_lr):
        print("[*] Symbol Resolution:")
        if stacked_pc:
            print("  Crash location (PC):")
            print(resolve_symbol(stacked_pc, args.elf, args.addr2line))
        if stacked_lr:
            print("  Caller location (LR):")
            print(resolve_symbol(stacked_lr, args.elf, args.addr2line))
        print("----------------------------------------------------")
    
    # 4. Decode HFSR
    hfsr_details = decode_hfsr(hfsr_val)
    if hfsr_details:
        print("[*] HFSR Details:")
        for line in hfsr_details:
            print(f"  {line}")
    else:
        print("[*] HFSR: No bits set (HardFault not directly indicated here).")
        
    # 5. Decode CFSR
    cfsr_details = decode_cfsr(cfsr_val)
    
    faults_found = False
    
    if cfsr_details["mmfsr_report"]:
        faults_found = True
        print("\n[*] MemManage Faults (MMFSR):")
        for line in cfsr_details["mmfsr_report"]:
            print(f"  {line}")
        if cfsr_details["mmfar_valid"]:
            print(f"  --> MMARVALID: MemManage Fault Address Register (MMFAR) is VALID.")
            print(f"  --> CRASH ADDRESS: 0x{mmfar_val:08X}")
            if mmfar_val == 0:
                print("  --> DIAGNOSIS: NULL pointer dereference (Read/Write at 0x00000000).")
                
    if cfsr_details["bfsr_report"]:
        faults_found = True
        print("\n[*] Bus Faults (BFSR):")
        for line in cfsr_details["bfsr_report"]:
            print(f"  {line}")
        if cfsr_details["bfar_valid"]:
            print(f"  --> BFARVALID: BusFault Address Register (BFAR) is VALID.")
            print(f"  --> CRASH ADDRESS: 0x{bfar_val:08X}")
            if bfar_val == 0:
                print("  --> DIAGNOSIS: NULL pointer access or illegal bus transaction at 0x00000000.")
 
    if cfsr_details["ufsr_report"]:
        faults_found = True
        print("\n[*] Usage Faults (UFSR):")
        for line in cfsr_details["ufsr_report"]:
            print(f"  {line}")
            
    if not faults_found and not hfsr_details:
        print("\n[!] No active fault flag identified in CFSR/HFSR.")
        print("    If a crash happened, ensure the register values are from the active crash dump context.")
    
    print("====================================================")

if __name__ == "__main__":
    main()
