#!/usr/bin/env python3
"""
Datasheet PDF Parser for Hardware Registers and Bitfields.
Extracts register names, base addresses, offsets, bitfields, access types,
and descriptions from semiconductor reference manuals (like STM32) using pdfplumber.
"""

import os
import sys
import json
import argparse
import re
import pdfplumber

def clean_text(text):
    """Clean up whitespace and newlines from PDF text."""
    if not text:
        return ""
    # Replace multiple whitespace/newlines with a single space
    return re.sub(r'\s+', ' ', str(text)).strip()

class DatasheetParser:
    def __init__(self, pdf_path):
        self.pdf_path = pdf_path
        self.registers = []
        self.peripherals = {}
        
    def parse(self, start_page=1, end_page=None):
        print(f"[*] Opening PDF: {self.pdf_path}")
        with pdfplumber.open(self.pdf_path) as pdf:
            total_pages = len(pdf.pages)
            last_page = end_page if end_page else total_pages
            
            print(f"[*] Parsing pages {start_page} to {last_page} of {total_pages}...")
            
            for page_num in range(start_page - 1, last_page):
                page = pdf.pages[page_num]
                self._parse_page(page, page_num + 1)
                
        return {
            "peripherals": self.peripherals,
            "registers": self.registers
        }

    def _parse_page(self, page, page_idx):
        text = page.extract_text() or ""
        
        # Check if page might contain register descriptions
        # Look for keywords like "Register", "Offset", "Reset value"
        is_register_page = any(kw in text for kw in ["Register", "Offset", "Reset value", "bitfield"])
        
        if is_register_page:
            self._parse_prose_page_registers(text)
            
        # Extract tables
        tables = page.extract_tables()
        if not tables:
            return
            
        for table in tables:
            if not table or len(table) < 2:
                continue
                
            # Heuristic 1: Is this a peripheral base address table?
            if any("base address" in clean_text(str(cell)).lower() for row in table for cell in row if cell):
                self._parse_peripheral_table(table)
                continue
                
            # Heuristic 2: Is this a register bitfield layout table (often has 32 cells or headers representing bits)?
            # Or is it a register description table listing bits, names, access, resets?
            headers = [clean_text(str(cell)).lower() for cell in table[0] if cell]
            
            # Check for bit description table columns: "bit", "name", "access", "reset", "description"
            is_bit_desc_table = False
            bit_col_idx = -1
            name_col_idx = -1
            desc_col_idx = -1
            access_col_idx = -1
            reset_col_idx = -1
            
            for idx, h in enumerate(headers):
                if "bit" in h:
                    bit_col_idx = idx
                elif "name" in h or "signal" in h:
                    name_col_idx = idx
                elif "desc" in h:
                    desc_col_idx = idx
                elif "access" in h or "type" in h:
                    access_col_idx = idx
                elif "reset" in h:
                    reset_col_idx = idx
            
            # If we matched enough columns, parse it as a bit description table
            if bit_col_idx != -1 and (name_col_idx != -1 or desc_col_idx != -1):
                self._parse_bit_description_table(table, bit_col_idx, name_col_idx, access_col_idx, reset_col_idx, desc_col_idx, text)
                continue
                
            # Generic table parser fallback for register lists (e.g. register map tables)
            if any(h in ["register", "offset", "description"] for h in headers):
                self._parse_register_map_table(table)

    def _parse_prose_page_registers(self, text):
        """Parse register information and bitfields from prose text (STM32 style)."""
        # Find register name
        reg_match = re.search(r'register\s+\(([A-Z0-9_]+)\)', text, re.IGNORECASE)
        if not reg_match:
            reg_match = re.search(r'register\s+([A-Z0-9_]{3,20})', text, re.IGNORECASE)
        if not reg_match:
            reg_match = re.search(r'\(([A-Z0-9_]+)\)', text)
        if not reg_match:
            reg_match = re.search(r'\b([A-Z0-9]{3,15}_[A-Z0-9_]{1,15})\b', text)
            
        if not reg_match:
            return
            
        reg_name = reg_match.group(1)
        
        # Find offset
        offset_match = re.search(r'(?:Address offset|Offset):\s*(0x[0-9A-Fa-f]+)', text, re.IGNORECASE)
        if not offset_match:
            return
        offset = offset_match.group(1)
        
        # Find reset value
        reset_match = re.search(r'Reset value:\s*(0x[0-9A-Fa-f\s]+|[0-9\sXx]+)', text, re.IGNORECASE)
        reset_val = reset_match.group(1).strip() if reset_match else ""
        
        # Find or create register
        register = next((r for r in self.registers if r["name"] == reg_name), None)
        if not register:
            register = {
                "name": reg_name,
                "offset": offset,
                "reset_value": reset_val,
                "description": f"Extracted from prose page describing {reg_name}",
                "fields": []
            }
            self.registers.append(register)
        else:
            if offset and not register["offset"]:
                register["offset"] = offset
            if reset_val and not register["reset_value"]:
                register["reset_value"] = reset_val

        # Parse bitfields using regex
        pattern = r'(?:Bits|Bit)\s+(\d+(?::\d+)?)\s+([A-Za-z0-9_]+(?:\[\d+:\d+\])?):?\s*(.*?)(?=(?:Bits|Bit)\s+\d+(?::\d+)?|\d+\.\d+\.\d+|\bAddress offset:|\Z)'
        matches = re.findall(pattern, text, re.DOTALL)
        
        if matches:
            print(f"[+] Found {len(matches)} prose bitfields for {reg_name}")
            for m in matches:
                bits, name, desc = m
                desc_clean = desc.strip().replace('\n', ' ')
                
                # Clean name if it has brackets
                f_name = name
                if "reserve" in name.lower() or "reserve" in desc_clean.lower():
                    f_name = "Reserved"
                    
                field = {
                    "bits": bits,
                    "name": f_name,
                    "access": "rw",
                    "reset": "0",
                    "description": desc_clean
                }
                
                # Update or append field
                existing_field = next((f for f in register["fields"] if f["bits"] == bits), None)
                if existing_field:
                    existing_field.update(field)
                else:
                    register["fields"].append(field)

    def _parse_peripheral_table(self, table):
        """Extract peripheral base addresses."""
        print("[+] Found peripheral base address table")
        headers = [clean_text(str(cell)).lower() for cell in table[0] if cell]
        
        name_idx, addr_idx = -1, -1
        for idx, h in enumerate(headers):
            if "peripheral" in h or "name" in h or "bus" in h:
                name_idx = idx
            elif "base address" in h or "address" in h:
                addr_idx = idx
                
        if name_idx == -1 or addr_idx == -1:
            # Fallback to defaults
            name_idx = 0
            addr_idx = 1 if len(table[0]) > 1 else 0
            
        for row in table[1:]:
            if not row or len(row) <= max(name_idx, addr_idx):
                continue
            name = clean_text(row[name_idx])
            addr = clean_text(row[addr_idx])
            # Validate hex address
            if name and addr and ("0x" in addr.lower() or re.search(r'[0-9A-Fa-f]{8}', addr)):
                self.peripherals[name] = {
                    "base_address": addr,
                    "description": clean_text(row[-1]) if len(row) > max(name_idx, addr_idx) + 1 else ""
                }

    def _parse_register_map_table(self, table):
        """Extract register names, offsets, and reset values from register map tables."""
        headers = [clean_text(str(cell)).lower() for cell in table[0] if cell]
        
        name_idx, offset_idx, reset_idx = -1, -1, -1
        for idx, h in enumerate(headers):
            if "register" in h or "name" in h:
                name_idx = idx
            elif "offset" in h or "address" in h:
                offset_idx = idx
            elif "reset" in h:
                reset_idx = idx
                
        if name_idx == -1 or offset_idx == -1:
            return
            
        for row in table[1:]:
            if not row or len(row) <= max(name_idx, offset_idx):
                continue
            name = clean_text(row[name_idx])
            offset = clean_text(row[offset_idx])
            reset = clean_text(row[reset_idx]) if reset_idx != -1 and len(row) > reset_idx else ""
            
            if name and offset and ("0x" in offset.lower() or re.search(r'[0-9A-Fa-f]', offset)):
                # Check if register already exists
                existing = next((r for r in self.registers if r["name"] == name), None)
                if existing:
                    existing["offset"] = offset
                    if reset:
                        existing["reset_value"] = reset
                else:
                    self.registers.append({
                        "name": name,
                        "offset": offset,
                        "reset_value": reset,
                        "description": "",
                        "fields": []
                    })

    def _parse_bit_description_table(self, table, bit_idx, name_idx, access_idx, reset_idx, desc_idx, page_text):
        """Parse register bit details."""
        # First, try to extract the register name from the page text (headers, etc.)
        # Often: "Register Name (REG_NAME)" or "Offset: 0xXX"
        reg_name_match = re.search(r'([A-Z0-9]+_[A-Z0-9]+|[A-Z0-9]{3,10})\b', page_text)
        reg_name = reg_name_match.group(1) if reg_name_match else "UNKNOWN_REG"
        
        # Check if we have an offset or description in page text
        offset_match = re.search(r'[Oo]ffset:\s*(0x[0-9A-Fa-f]+)', page_text)
        offset = offset_match.group(1) if offset_match else ""
        
        reset_match = re.search(r'[Rr]eset\s+[Vv]alue:\s*(0x[0-9A-Fa-f]+|[0-9]+)', page_text)
        reset_val = reset_match.group(1) if reset_match else ""
        
        # Find or create register
        register = next((r for r in self.registers if r["name"] == reg_name), None)
        if not register:
            register = {
                "name": reg_name,
                "offset": offset,
                "reset_value": reset_val,
                "description": f"Extracted from page describing {reg_name}",
                "fields": []
            }
            self.registers.append(register)
        else:
            if offset and not register["offset"]:
                register["offset"] = offset
            if reset_val and not register["reset_value"]:
                register["reset_value"] = reset_val

        print(f"[+] Parsing bitfields for register: {register['name']}")
        
        for row in table[1:]:
            if not row or len(row) <= max(bit_idx, name_idx if name_idx != -1 else 0):
                continue
                
            bits = clean_text(row[bit_idx])
            # Validate bit string (e.g., "15", "14:12", "0")
            if not re.match(r'^\d+(:\d+)?$', bits):
                continue
                
            name = clean_text(row[name_idx]) if name_idx != -1 else f"FIELD_{bits}"
            access = clean_text(row[access_idx]) if access_idx != -1 and len(row) > access_idx else "rw"
            reset = clean_text(row[reset_idx]) if reset_idx != -1 and len(row) > reset_idx else "0"
            desc = clean_text(row[desc_idx]) if desc_idx != -1 and len(row) > desc_idx else ""
            
            # Check if this field is reserved
            if "reserve" in name.lower() or "reserve" in desc.lower():
                name = "Reserved"
                
            field = {
                "bits": bits,
                "name": name,
                "access": access,
                "reset": reset,
                "description": desc
            }
            
            # Update or append
            existing_field = next((f for f in register["fields"] if f["bits"] == bits), None)
            if existing_field:
                existing_field.update(field)
            else:
                register["fields"].append(field)

def main():
    parser = argparse.ArgumentParser(description="Parse semiconductor datasheet PDFs into structured JSON register maps.")
    parser.add_argument("pdf", help="Path to the datasheet/reference manual PDF file")
    parser.add_argument("-o", "--output", help="Path to output JSON file (default: stdout)", default=None)
    parser.add_argument("-s", "--start", type=int, default=1, help="Start page (default: 1)")
    parser.add_argument("-e", "--end", type=int, default=None, help="End page (default: end of document)")
    
    args = parser.parse_args()
    
    if not os.path.exists(args.pdf):
        print(f"Error: File not found: {args.pdf}", file=sys.stderr)
        sys.exit(1)
        
    parser = DatasheetParser(args.pdf)
    data = parser.parse(start_page=args.start, end_page=args.end)
    
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        print(f"[*] Successfully wrote register map to: {args.output}")
    else:
        print(json.dumps(data, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
