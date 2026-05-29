.
|-- .env
|-- .env.example
|-- .gitignore
|-- .python-version
|-- AGENTS.md
|-- pyproject.toml
|-- README.md
|-- settings.exmaple.yaml
|-- settings.yaml
|-- .codex/
|   |-- code_map_ignore
|   |-- config.toml
|   |-- hooks.json
|   `-- scripts/
|       `-- update_code_map.py
|-- data/
|   `-- .gitkeep
|-- docs/
|   |-- live-assistant-prd.md
|   |-- live-distributed-architecture.md
|   `-- xhs-live-room-automation-notes.md
|-- src/
|   `-- smhelper/
|       |-- __init__.py
|       |-- cli.py
|       |-- core/
|       |   |-- __init__.py
|       |   |-- clock.py
|       |   |-- config.py
|       |   |-- exceptions.py
|       |   `-- ids.py
|       `-- live_assistant/
|           |-- __init__.py
|           |-- application/
|           |   |-- __init__.py
|           |   |-- commands.py
|           |   |-- exceptions.py
|           |   |-- handlers.py
|           |   `-- ports.py
|           |-- domain/
|           |   |-- __init__.py
|           |   |-- exceptions.py
|           |   |-- models.py
|           |   |-- repositories.py
|           |   `-- services.py
|           |-- infrastructure/
|           |   |-- __init__.py
|           |   |-- cloakbrowser.py
|           |   |-- local_state.py
|           |   `-- memory.py
|           `-- interfaces/
|               |-- __init__.py
|               `-- cli.py
`-- tests/
    |-- test_cli.py
    |-- test_update_code_map.py
    |-- core/
    |   |-- test_config.py
    |   `-- test_ids.py
    `-- live_assistant/
        |-- test_cloakbrowser_login.py
        |-- test_handlers.py
        |-- test_live_assistant_cli.py
        `-- test_local_state.py
