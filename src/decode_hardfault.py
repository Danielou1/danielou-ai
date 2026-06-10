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

def main():
    parser = argparse.ArgumentParser(description="ARM Cortex-M HardFault and System Control Block (SCB) Register Decoder.")
    parser.add_argument("--cfsr", help="Configurable Fault Status Register (CFSR) value in hex (e.g. 0x00010000)", default="0x0")
    parser.add_argument("--hfsr", help="HardFault Status Register (HFSR) value in hex (e.g. 0x40000000)", default="0x0")
    parser.add_argument("--bfar", help="BusFault Address Register (BFAR) value in hex", default="0x0")
    parser.add_argument("--mmfar", help="MemManage Fault Address Register (MMFAR) value in hex", default="0x0")
    
    args = parser.parse_args()
    
    try:
        cfsr_val = int(args.cfsr, 16)
        hfsr_val = int(args.hfsr, 16)
        bfar_val = int(args.bfar, 16)
        mmfar_val = int(args.mmfar, 16)
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
    print("----------------------------------------------------")
    
    # Decode HFSR
    hfsr_details = decode_hfsr(hfsr_val)
    if hfsr_details:
        print("[*] HFSR Details:")
        for line in hfsr_details:
            print(f"  {line}")
    else:
        print("[*] HFSR: No bits set (HardFault not directly indicated here).")
        
    # Decode CFSR
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
