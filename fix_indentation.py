#!/usr/bin/env python3
"""Fix indentation issues in app.py"""

with open("ui/desktop/app.py", "r", encoding="utf-8") as f:
    lines = f.readlines()

# Fix the try-except block in _fetch_balance method
# The block is from line 1573 to 1597

# First, let's identify where the _fetch_balance method starts
fetch_balance_start = None
for i, line in enumerate(lines):
    if "def _fetch_balance(self):" in line:
        fetch_balance_start = i
        break

if fetch_balance_start is None:
    print("Could not find _fetch_balance method")
    exit(1)

print(f"Found _fetch_balance at line {fetch_balance_start + 1}")

# Find the try statement
try_line = None
for i in range(fetch_balance_start, min(fetch_balance_start + 50, len(lines))):
    if lines[i].strip() == "try:":
        try_line = i
        break

if try_line is None:
    print("Could not find try statement")
    exit(1)

print(f"Found try at line {try_line + 1}")

# Find the except statement
except_line = None
for i in range(try_line, min(try_line + 30, len(lines))):
    if lines[i].strip().startswith("except Exception"):
        except_line = i
        break

if except_line is None:
    print("Could not find except statement")
    exit(1)

print(f"Found except at line {except_line + 1}")

# Find the next method def after except
next_def = None
for i in range(except_line, min(except_line + 20, len(lines))):
    if lines[i].strip().startswith("def ") and i > except_line:
        next_def = i
        break

if next_def is None:
    print("Could not find next method")
    exit(1)

print(f"Found next def at line {next_def + 1}")

# Now let's check and fix the indentation
# try should be at 8 spaces (inside method which is at 4)
# try block content should be at 12 spaces
# except should be at 8 spaces
# except block content should be at 12 spaces

print("\nAnalyzing indentation...")
for i in range(try_line, min(try_line + 5, len(lines))):
    line = lines[i]
    spaces = len(line) - len(line.lstrip())
    print(f"Line {i + 1}: {spaces} spaces - {line[:60]}")

print("\n...")
for i in range(except_line - 2, min(except_line + 5, len(lines))):
    line = lines[i]
    spaces = len(line) - len(line.lstrip())
    print(f"Line {i + 1}: {spaces} spaces - {line[:60]}")

# The issue is that the try block is not properly closed before except
# Let's look at the structure more carefully
print("\n\nLooking at structure around except...")
for i in range(except_line - 10, min(except_line + 10, len(lines))):
    line = lines[i]
    spaces = len(line) - len(line.lstrip())
    print(f"Line {i + 1}: {spaces} spaces - {repr(line[:80])}")
