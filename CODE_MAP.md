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
|       |-- accounts/
|       |   |-- __init__.py
|       |   `-- domain/
|       |       |-- __init__.py
|       |       |-- account_auth_state.py
|       |       |-- account_node_binding.py
|       |       `-- platform_account.py
|       |-- core/
|       |   |-- __init__.py
|       |   |-- clock.py
|       |   |-- config.py
|       |   |-- exceptions.py
|       |   `-- ids.py
|       |-- infrastructure/
|       |   |-- __init__.py
|       |   |-- ai/
|       |   |   |-- __init__.py
|       |   |   `-- litellm_question_generator.py
|       |   |-- asr/
|       |   |   |-- __init__.py
|       |   |   `-- provider_adapter.py
|       |   |-- media/
|       |   |   |-- __init__.py
|       |   |   `-- ffmpeg/
|       |   |       |-- __init__.py
|       |   |       |-- artifact_extractor.py
|       |   |       |-- audio.py
|       |   |       |-- runner.py
|       |   |       |-- screenshots.py
|       |   |       |-- segment_recorder.py
|       |   |       `-- segment_scanner.py
|       |   |-- persistence/
|       |   |   |-- __init__.py
|       |   |   `-- sqlalchemy/
|       |   |       |-- __init__.py
|       |   |       |-- account_entry_dispatcher.py
|       |   |       |-- account_entry_planner.py
|       |   |       |-- account_session_restarter.py
|       |   |       |-- accounts.py
|       |   |       |-- base.py
|       |   |       |-- candidate_dispatcher.py
|       |   |       |-- candidate_reviewer.py
|       |   |       |-- live.py
|       |   |       |-- live_doctor.py
|       |   |       |-- live_seed_dev.py
|       |   |       |-- live_task_observer.py
|       |   |       |-- live_task_shutdown_coordinator.py
|       |   |       |-- live_task_starter.py
|       |   |       |-- live_task_terminator.py
|       |   |       |-- schema.py
|       |   |       |-- segment_processor.py
|       |   |       |-- segment_processor_factory.py
|       |   |       |-- segment_task_scheduler.py
|       |   |       |-- session.py
|       |   |       `-- workers.py
|       |   `-- task_queue/
|       |       |-- __init__.py
|       |       `-- celery/
|       |           |-- __init__.py
|       |           |-- app.py
|       |           |-- center_api_client.py
|       |           |-- center_handler.py
|       |           |-- center_publisher.py
|       |           |-- center_runtime.py
|       |           |-- center_tasks.py
|       |           |-- center_worker.py
|       |           |-- center_worker_runtime.py
|       |           |-- node_handler.py
|       |           |-- node_tasks.py
|       |           |-- node_worker_runtime.py
|       |           |-- publisher.py
|       |           `-- tasks.py
|       |-- live/
|       |   |-- __init__.py
|       |   |-- application/
|       |   |   |-- __init__.py
|       |   |   |-- ports/
|       |   |   |   |-- __init__.py
|       |   |   |   |-- live_stream_observer.py
|       |   |   |   |-- media_artifacts.py
|       |   |   |   |-- question_generator.py
|       |   |   |   `-- speech_to_text.py
|       |   |   `-- use_cases/
|       |   |       |-- __init__.py
|       |   |       |-- approve_candidate_question.py
|       |   |       |-- plan_account_entries.py
|       |   |       `-- process_segment.py
|       |   `-- domain/
|       |       |-- __init__.py
|       |       |-- account_live_session.py
|       |       |-- candidate_question.py
|       |       |-- dispatch_job.py
|       |       |-- send_attempt.py
|       |       |-- transcript.py
|       |       `-- policies/
|       |           |-- __init__.py
|       |           |-- account_entry_policy.py
|       |           |-- send_account_policy.py
|       |           `-- shutdown_policy.py
|       |-- live_assistant/
|       |   |-- __init__.py
|       |   |-- application/
|       |   |   |-- __init__.py
|       |   |   |-- commands.py
|       |   |   |-- exceptions.py
|       |   |   |-- handlers.py
|       |   |   `-- ports.py
|       |   |-- domain/
|       |   |   |-- __init__.py
|       |   |   |-- exceptions.py
|       |   |   |-- models.py
|       |   |   |-- repositories.py
|       |   |   `-- services.py
|       |   |-- infrastructure/
|       |   |   |-- __init__.py
|       |   |   |-- cloakbrowser.py
|       |   |   |-- local_state.py
|       |   |   `-- memory.py
|       |   `-- interfaces/
|       |       |-- __init__.py
|       |       `-- cli.py
|       |-- platforms/
|       |   |-- __init__.py
|       |   `-- xhs/
|       |       |-- __init__.py
|       |       |-- celery_worker.py
|       |       |-- worker_runtime.py
|       |       `-- browser/
|       |           |-- __init__.py
|       |           |-- cloakbrowser_live_room.py
|       |           |-- cloakbrowser_observer.py
|       |           |-- live_room_operator.py
|       |           |-- selectors.py
|       |           `-- stream_discovery.py
|       |-- web/
|       |   |-- __init__.py
|       |   |-- admin.py
|       |   |-- api.py
|       |   |-- app.py
|       |   `-- admin_views/
|       |       |-- __init__.py
|       |       |-- accounts.py
|       |       |-- candidates.py
|       |       |-- dispatch_jobs.py
|       |       |-- live_tasks.py
|       |       |-- segments.py
|       |       |-- sessions.py
|       |       `-- workers.py
|       `-- workers/
|           |-- __init__.py
|           `-- domain/
|               |-- __init__.py
|               |-- rendezvous_hashing.py
|               `-- worker_node.py
`-- tests/
    |-- test_cli.py
    |-- test_update_code_map.py
    |-- accounts/
    |   `-- test_platform_account.py
    |-- core/
    |   |-- test_config.py
    |   `-- test_ids.py
    |-- infrastructure/
    |   |-- ai/
    |   |   `-- test_litellm_question_generator.py
    |   |-- asr/
    |   |   `-- test_provider_adapter.py
    |   |-- media/
    |   |   |-- test_ffmpeg_artifact_extractor.py
    |   |   `-- test_ffmpeg_tools.py
    |   |-- persistence/
    |   |   |-- test_account_entry_dispatcher.py
    |   |   |-- test_account_entry_planner.py
    |   |   |-- test_account_session_restarter.py
    |   |   |-- test_candidate_dispatcher.py
    |   |   |-- test_candidate_reviewer.py
    |   |   |-- test_live_task_observer_runner.py
    |   |   |-- test_live_task_shutdown_coordinator.py
    |   |   |-- test_live_task_starter.py
    |   |   |-- test_live_task_terminator.py
    |   |   |-- test_segment_processor.py
    |   |   |-- test_segment_processor_factory.py
    |   |   |-- test_segment_task_scheduler.py
    |   |   |-- test_sqlalchemy_records.py
    |   |   `-- test_sqlalchemy_session.py
    |   `-- task_queue/
    |       |-- test_celery_publisher.py
    |       |-- test_center_api_client.py
    |       |-- test_center_handler.py
    |       |-- test_center_publisher.py
    |       |-- test_center_runtime.py
    |       |-- test_center_task_registration.py
    |       |-- test_center_worker.py
    |       |-- test_center_worker_runtime.py
    |       |-- test_node_browser_task_handler.py
    |       |-- test_node_task_registration.py
    |       `-- test_node_worker_runtime.py
    |-- live/
    |   |-- test_account_live_session_policy.py
    |   |-- test_approve_candidate_question.py
    |   |-- test_candidate_and_dispatch.py
    |   |-- test_live_task_shutdown_policy.py
    |   |-- test_plan_account_entries.py
    |   |-- test_process_segment.py
    |   `-- test_send_account_policy.py
    |-- live_assistant/
    |   |-- test_cloakbrowser_login.py
    |   |-- test_handlers.py
    |   |-- test_live_assistant_cli.py
    |   `-- test_local_state.py
    |-- platforms/
    |   `-- xhs/
    |       |-- test_celery_worker.py
    |       |-- test_cloakbrowser_live_room.py
    |       |-- test_cloakbrowser_observer.py
    |       |-- test_live_room_operator.py
    |       |-- test_stream_discovery.py
    |       `-- test_worker_runtime.py
    |-- web/
    |   |-- test_account_storage_state_api.py
    |   |-- test_admin_app.py
    |   |-- test_candidate_approve_action.py
    |   `-- test_live_task_observe_action.py
    `-- workers/
        `-- test_rendezvous_hashing.py
