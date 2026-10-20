# minitools

Small personal tools that make working with the desktop on my computer
(Linux Mint, Cinnamon) more convenient: tray icons, small GUIs, helper
scripts.

## Layout

Each mini-tool lives in its own subdirectory, self-contained:

```
<tool>/
  README.md     what the tool does and how to use it
  install.sh    installs (and with --uninstall removes) the tool
  ...           the tool's sources
```

Nothing is shared between tools. Installing one tool means running its
`install.sh`.

## Tools

| Tool                  | Description                                              |
|-----------------------|----------------------------------------------------------|
| [perfctl](perfctl/)   | Tray icon for CPU cooler fan boost and CPU freq boost   |

## Note to Claude

When changing this repository, keep the structure above:

- One subdirectory per tool, with its own `README.md` and `install.sh`.
- No cross-tool dependencies; each tool can be installed on its own.
- Keep the tools table in this README up to date when tools are added,
  removed or renamed.
- `plan.md` in the root is for planning work in progress, not documentation.
