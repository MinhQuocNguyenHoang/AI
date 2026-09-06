VENV_DIR := quoc_env
PYTHON := $(VENV_DIR)/bin/python3
PIP := $(VENV_DIR)/bin/pip
REQ := requirements.txt

.PHONY: help venv install install-pkgs reinstall clean

help:
	@echo "Usage: make <target> [PKGS=\"pkg1 pkg2\"]"
	@echo "  venv            Create virtualenv $(VENV_DIR) if missing"
	@echo "  install         Install packages from $(REQ) into venv"
	@echo "  install-pkgs    Install extra packages: make install-pkgs PKGS=\"pkg1 pkg2\""
	@echo "  reinstall       Recreate venv and install requirements"
	@echo "  clean           Remove the venv"

venv:
	@if [ ! -d "$(VENV_DIR)" ]; then python3 -m venv $(VENV_DIR); fi
	@$(PYTHON) -m ensurepip --upgrade >/dev/null 2>&1 || true
	@$(PYTHON) -m pip install --upgrade pip setuptools wheel

install: venv
	@$(PIP) install -r $(REQ)

install-pkgs: venv
	@if [ -z "$(PKGS)" ]; then echo "Specify PKGS=\"pkg1 pkg2\""; exit 1; fi
	@$(PIP) install $(PKGS)

reinstall:
	@rm -rf $(VENV_DIR)
	@$(MAKE) venv
	@$(MAKE) install

clean:
	@rm -rf $(VENV_DIR)
