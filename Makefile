test:
	python3 -m pytest -q
demo:
	python3 demo.py examples
bench:
	python3 -m measures.benchmark 5
