# VHS tape — reproducible terminal GIF for the README.
# Install VHS (https://github.com/charmbracelet/vhs), then run:  vhs docs/demo.tape
# Produces docs/demo.gif. Tweak the Sleep values to taste.

Output docs/demo.gif

Set Shell pwsh
Set FontSize 16
Set Width 1280
Set Height 760
Set Padding 16
Set Theme "Tokyo Night"

# --- One-scan-everything: the value proposition up front -----------------
Type "sifty checkup"  Sleep 700ms  Enter
Sleep 5s

# --- Junk scan: reclaimable space per category ---------------------------
Type "sifty junk scan"  Sleep 700ms  Enter
Sleep 4s

# --- Disk volumes --------------------------------------------------------
Type "sifty disk volumes"  Sleep 700ms  Enter
Sleep 3s

# --- The interactive TUI -------------------------------------------------
Type "sifty tui"  Sleep 700ms  Enter
Sleep 3s
Down  Sleep 1s          # move down the sidebar (Clean)
Enter Sleep 2s
Down  Sleep 1s          # Disk
Enter Sleep 2s
Down  Sleep 1s          # Apps
Enter Sleep 2s
Ctrl+P  Sleep 1500ms    # command palette
Type "ai"  Sleep 1500ms
Escape  Sleep 1s
Type "q"                # quit the TUI
Sleep 2s
