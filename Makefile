SKILL_NAME := jetbriefcheck
VERSION := $(shell sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' skill/version.json | head -1)

# Prefer the repo venv: pytest and PyMuPDF live there, and neither is
# necessarily on PATH. `make release` gates on `make test`, so resolving this
# wrongly turns a release into a spurious failure.
PYTHON := $(shell [ -x .venv/bin/python ] && echo .venv/bin/python || echo python3)

# Plugin archive first in the list because it is how most users install: a
# Cowork plugin, either from jet-hub or by direct upload of this zip.
PLUGIN_ZIP := $(SKILL_NAME)-plugin-$(VERSION).zip
SKILL_ZIP  := $(SKILL_NAME)-skill-$(VERSION).zip

.PHONY: package package-plugin package-all clean test version-check release check-assets
.PHONY: build-plugin build-skill

# Public package targets clean first, then delegate to a build-* recipe.
#
# The clean is load-bearing, not tidiness. `zip -r` ADDS to an existing archive
# rather than replacing it, so a rebuild over a stale zip keeps every file any
# earlier build ever put there. That shipped: the old build_zip.sh had no
# clean, and jetbriefcheck.zip had accumulated app.py, config.py, web/,
# deploy_skill.py, install.sh, README.md and CLAUDE.md — none of which have
# ever been part of skill/. Releases were unaffected only because CI builds on
# a fresh checkout where the gitignored zip does not exist.
package: clean build-plugin
package-plugin: clean build-plugin
package-all: clean build-plugin build-skill

# Plugin archive for Cowork and marketplace upload: the manifest at the archive
# root plus the skill tree it names in plugin.json's "skills": "./skill".
# This is the primary artifact.
build-plugin:
	zip -r $(PLUGIN_ZIP) .claude-plugin/plugin.json skill/ \
		-x "skill/.venv/*" "*/__pycache__/*" "*.pyc"

# Standalone skill zip: jetbriefcheck/ at the archive root, no manifest. For a
# manual drop into ~/.claude/skills/, or the Cowork "Skills +" upload. Kept
# because it is what the pre-2.5.0 install instructions pointed at.
build-skill:
	@rm -rf .build && mkdir -p .build/$(SKILL_NAME)
	@cp -R skill/. .build/$(SKILL_NAME)/
	@find .build -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find .build -name '*.pyc' -delete 2>/dev/null || true
	@rm -rf .build/$(SKILL_NAME)/.venv
	cd .build && zip -r ../$(SKILL_ZIP) $(SKILL_NAME)/
	@rm -rf .build

clean:
	rm -f $(SKILL_NAME)-plugin-*.zip $(SKILL_NAME)-skill-*.zip $(SKILL_NAME).zip
	rm -rf .build

test:
	$(PYTHON) -m pytest tests/ -q

# The version lives in three files and has drifted before — the 2.4.0 release
# left .claude-plugin/plugin.json behind while version.json and SKILL.md moved
# on. tests/test_version_check.py asserts the same thing; this target gates a
# release without running the suite.
version-check:
	@V="$(VERSION)"; \
	PV=$$(sed -n 's/.*"version"[[:space:]]*:[[:space:]]*"\([^"]*\)".*/\1/p' .claude-plugin/plugin.json | head -1); \
	SV=$$(sed -n 's/^version:[[:space:]]*\(.*\)$$/\1/p' skill/SKILL.md | head -1); \
	if [ "$$V" != "$$PV" ] || [ "$$V" != "$$SV" ]; then \
	  echo "VERSION DRIFT: version.json=$$V plugin.json=$$PV SKILL.md=$$SV"; exit 1; \
	fi; \
	echo "version: $$V consistent across version.json, plugin.json, SKILL.md."

# NOTE: jet-hub pins each plugin to a release TAG, not to a branch. Its
# sync-plugin-releases workflow polls /releases/latest every 30 minutes and
# bumps the pin, so plugin users get this build once the GitHub release is
# PUBLISHED — pushing main alone ships nothing. Draft and prerelease tags are
# excluded by that endpoint, so a release left as a draft is invisible to them.
# The zips below are attached for direct uploads.
release: version-check test package-all
	@git tag -a "v$(VERSION)" -m "Release v$(VERSION)" && \
	git push origin main && \
	git push origin "v$(VERSION)" && \
	gh release create "v$(VERSION)" $(PLUGIN_ZIP) $(SKILL_ZIP) --title "v$(VERSION)" --generate-notes && \
	$(MAKE) --no-print-directory check-assets TAG="v$(VERSION)" ASSETS="$(PLUGIN_ZIP) $(SKILL_ZIP)" && \
	echo "Released v$(VERSION)"

# `gh release create` can exit 0 after silently skipping an asset — jetredline
# v4.19.1 announced success while missing one of its three zips, and it was
# caught by eye. Assert every expected asset actually landed, retry once, then
# fail hard.
check-assets:
	@test -n "$(TAG)" || { echo "check-assets: TAG not set"; exit 1; }
	@for f in $(ASSETS); do \
	  if ! gh release view "$(TAG)" --json assets --jq '.assets[].name' | grep -qx "$$f"; then \
	    echo "MISSING: $$f did not attach to $(TAG); retrying upload"; \
	    gh release upload "$(TAG)" "$$f" --clobber || true; \
	  fi; \
	done
	@missing=0; \
	for f in $(ASSETS); do \
	  gh release view "$(TAG)" --json assets --jq '.assets[].name' | grep -qx "$$f" || \
	    { echo "FAIL: $$f is still not attached to $(TAG)"; missing=1; }; \
	done; \
	[ $$missing -eq 0 ] || exit 1; \
	echo "assets verified on $(TAG): $(ASSETS)"
