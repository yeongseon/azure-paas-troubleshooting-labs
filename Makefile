.PHONY: help install serve build clean lint

help:
	@echo "Available targets:"
	@echo "  install  - Install dependencies"
	@echo "  serve    - Start local development server"
	@echo "  build    - Build MkDocs site (strict mode)"
	@echo "  clean    - Remove build artifacts"
	@echo "  lint     - Run markdown linter"

install:
	pip install mkdocs-material pymdown-extensions

serve:
	mkdocs serve

build:
	mkdocs build --strict

clean:
	rm -rf site/

lint:
	@echo "Checking markdown files..."
	@if command -v markdownlint-cli2 > /dev/null; then \
		markdownlint-cli2 "docs/**/*.md"; \
	else \
		echo "markdownlint-cli2 not installed. Run: npm install -g markdownlint-cli2"; \
	fi
