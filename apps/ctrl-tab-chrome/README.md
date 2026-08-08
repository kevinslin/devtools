# ctrl-tab-chrome

`ctrl-tab-chrome` is a local Chrome extension that makes plain `Ctrl+Tab` switch to the last used tab when focus is inside a normal web page.

## Install

1. Open `chrome://extensions`.
2. Enable Developer mode.
3. Choose `Load unpacked`.
4. Select `/Users/kevinlin/code/devtools/apps/ctrl-tab-chrome`.
5. Reload already-open pages if `Ctrl+Tab` does not work immediately there.

## Behavior

- Press `Ctrl+Tab` on a normal web page to jump to the most recently active tab in the same window.
- Press `Ctrl+Tab` again to toggle back to the previous tab.
- The extension starts tracking tab history after it is installed or reloaded.

## Limits

Chrome reserves browser-level shortcuts, so this extension does not use `chrome.commands` and cannot intercept `Ctrl+Tab` from Chrome UI surfaces such as the address bar, `chrome://` pages, the Web Store, or pages where content scripts are not allowed.

For local `file://` pages, enable `Allow access to file URLs` for the extension in `chrome://extensions` if you want the shortcut there.
