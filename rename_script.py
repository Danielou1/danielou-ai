import sys

file_path = 'rust/crates/rusty-claude-cli/src/main.rs'
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

content = content.replace('claw', 'danielou')
content = content.replace('CLAW', 'DANIELOU')

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Replacement completed.")
