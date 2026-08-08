# Devtools project layout

This schema describes how command-line tools and local applications are
organized in the devtools repository.

```text
devtools/
├── .mem.yaml                 # Registers the devtools memory base and schema.
├── AGENTS.md                 # Repository-wide agent instructions.
├── README.md                 # Human-facing project catalog and CLI index.
├── bin/                      # Compatibility symlinks for existing commands.
├── schemas/
│   └── devtools/
│       ├── README.md         # This layout guide.
│       └── schema.yaml       # Machine-readable project layout.
├── tools/
│   └── <project>/
│       ├── README.md         # Required human-facing tool documentation.
│       ├── AGENTS.md         # Optional project-specific agent instructions.
│       ├── bin/              # Project-owned executable entry points.
│       ├── docs/             # Optional architecture, flow, and reference docs.
│       ├── specs/            # Optional design and implementation specs.
│       └── src/              # Optional implementation sources.
└── apps/
    └── <project>/
        ├── README.md         # Required human-facing application documentation.
        ├── AGENTS.md         # Optional application-specific agent instructions.
        ├── bin/              # Optional application launchers.
        ├── docs/             # Optional supporting documentation.
        ├── specs/            # Optional design and implementation specs.
        └── src/              # Optional implementation sources.
```

Create optional files and directories only when a project needs them. Runtime
configuration belongs under `~/.config/<project>/`, not inside the project.

Named schemas are resolved from the nearest ancestor `schemas/` directory,
then `$HOME/.schemas/`, and finally the bundled `$mem` schemas.
