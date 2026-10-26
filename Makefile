.PHONY: test eval run

test:
	py tests/test_data_integrity.py
	py tests/test_core_engine.py
	py tests/test_core_engine_expanded.py
	py tests/test_server_api.py

eval:
	py src/eval_runner.py

run:
	py run.py
