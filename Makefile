.PHONY: gen-manifest check-manifest

gen-manifest:
	python3 scripts/gen_manifest.py -v

check-manifest:
	python3 scripts/check_manifest.py
