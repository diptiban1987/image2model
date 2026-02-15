#!/usr/bin/env python3
"""Update desktop app to include logo reference"""

import re

# Read the file
with open("ui/desktop/app.py", "r", encoding="utf-8") as f:
    content = f.read()

# Add logo method to ImageTo3DProApp class
logo_method = '''
    def _create_logo_widget(self, size=64):
        """Create a logo widget with gradient background."""
        from PySide6.QtWidgets import QWidget, QVBoxLayout, QLabel
        from PySide6.QtCore import Qt
        from PySide6.QtGui import QPixmap, QColor, QPainter, QLinearGradient, QFont
        
        logo_container = QWidget()
        logo_layout = QVBoxLayout(logo_container)
        logo_layout.setContentsMargins(0, 0, 0, 0)
        logo_layout.setSpacing(0)
        
        # Create logo label with styled text
        logo_label = QLabel("🎨")
        logo_label.setAlignment(Qt.AlignCenter)
        logo_label.setStyleSheet(f"""
            font-size: {size}px;
            background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                stop:0 #667eea, stop:1 #764ba2);
            border-radius: {size//4}px;
            padding: 10px;
            min-width: {size}px;
            min-height: {size}px;
        """)
        logo_layout.addWidget(logo_label)
        
        return logo_container
    
'''

# Find the right place to insert the method - after _build_ui method
# Insert after the last method in ImageTo3DProApp class
if "_create_logo_widget" not in content:
    # Find a good insertion point - after _refresh_system_info or similar
    pattern = r"(def _refresh_system_info\(self\):.*?)(\n    # ═══|$)"
    match = re.search(pattern, content, re.DOTALL)
    if match:
        insert_pos = match.end() - len(match.group(2))
        content = content[:insert_pos] + logo_method + content[insert_pos:]
        print("Added _create_logo_widget method")
    else:
        print("Could not find insertion point for logo method")

# Update login dialog to use logo
old_login_section = """# App title - compact
title = QLabel("🔒 Image → 3D Pro")
title.setAlignment(Qt.AlignCenter)
title.setStyleSheet(
"font-size: 24px; font-weight: 700; color: #60a5fa; margin-bottom: 4px;"
)
layout.addWidget(title)"""

new_login_section = '''# Logo and title section with visual branding
logo_container = QWidget()
logo_layout = QVBoxLayout(logo_container)
logo_layout.setContentsMargins(0, 0, 0, 0)
logo_layout.setSpacing(8)

logo_icon = QLabel("◈")
logo_icon.setAlignment(Qt.AlignCenter)
logo_icon.setStyleSheet("""
    font-size: 48px;
    color: transparent;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #667eea, stop:1 #764ba2, stop:0.5 #f093fb);
    background-clip: text;
    -webkit-background-clip: text;
    margin-bottom: 4px;
""")
logo_layout.addWidget(logo_icon)

# App title - compact
title = QLabel("🔒 ImageTo3D Pro")
title.setAlignment(Qt.AlignCenter)
title.setStyleSheet(
    "font-size: 24px; font-weight: 700; color: #60a5fa; margin-bottom: 4px;"
)
logo_layout.addWidget(title)

layout.addWidget(logo_container)'''

if old_login_section in content:
    content = content.replace(old_login_section, new_login_section)
    print("Updated login dialog with logo section")
else:
    print("Warning: Could not find login dialog title section to update")

# Update main app logo
old_main_logo = """# App logo area - compact
logo_container = QWidget()
logo_layout = QVBoxLayout(logo_container)
logo_layout.setContentsMargins(0, 0, 0, 0)
logo_layout.setSpacing(4)

logo = QLabel("🎨 Image → 3D Pro")
logo.setStyleSheet("font-size: 20px; font-weight: 700; color: #60a5fa;")
logo.setAlignment(Qt.AlignCenter)
logo_layout.addWidget(logo)"""

new_main_logo = '''# App logo area - compact with visual branding
logo_container = QWidget()
logo_layout = QVBoxLayout(logo_container)
logo_layout.setContentsMargins(0, 0, 0, 0)
logo_layout.setSpacing(6)

logo_icon = QLabel("◈")
logo_icon.setAlignment(Qt.AlignCenter)
logo_icon.setStyleSheet("""
    font-size: 36px;
    color: transparent;
    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
        stop:0 #667eea, stop:1 #764ba2);
    background-clip: text;
    -webkit-background-clip: text;
    margin-bottom: 4px;
""")
logo_layout.addWidget(logo_icon)

logo = QLabel("ImageTo3D Pro")
logo.setStyleSheet("font-size: 20px; font-weight: 700; color: #60a5fa;")
logo.setAlignment(Qt.AlignCenter)
logo_layout.addWidget(logo)'''

if old_main_logo in content:
    content = content.replace(old_main_logo, new_main_logo)
    print("Updated main window with logo")
else:
    print("Warning: Could not find main window logo section to update")

# Write the file back
with open("ui/desktop/app.py", "w", encoding="utf-8") as f:
    f.write(content)

print("\nDesktop app updated successfully!")
print("Logo assets are available in:")
print("  - ui/desktop/assets/logo.svg")
print("  - ui/desktop/assets/logo-icon.svg")
print("  - ui/desktop/assets/logo-wide.svg")
