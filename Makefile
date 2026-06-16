# comment: install/uninstall the lsc command and shell functions

# Override locations with e.g. `make install PREFIX=/usr/local` or
# `make install BINDIR=~/bin`. Defaults live under ~/.local, which needs no
# sudo. A leading ~ in an override is expanded (via eval echo) so it never
# lands on disk literally, regardless of the shell that invoked make.
PREFIX  ?= $(HOME)/.local
BINDIR  ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share/lsc
SCRIPT  := lsc.py

.PHONY: install uninstall test

install:
	@bindir=$$(eval echo "$(BINDIR)"); \
	datadir=$$(eval echo "$(DATADIR)"); \
	mkdir -p "$$bindir" "$$datadir"; \
	install -m 755 "$(SCRIPT)" "$$bindir/lsc"; \
	install -m 644 lsc.zsh "$$datadir/lsc.zsh"; \
	echo "installed $$bindir/lsc"; \
	echo "installed $$datadir/lsc.zsh"; \
	rp=$$(cd "$$bindir" 2>/dev/null && pwd -P); \
	: "rp is bindir with symlinks resolved, so a synced ~/tools -> iCloud" \
	  "symlink still matches a PATH entry written in its resolved form"; \
	case ":$$PATH:" in \
	  *":$$bindir:"*|*":$$rp:"*) ;; \
	  *) echo "note: $$bindir is not on your PATH; add it to use 'lsc'";; \
	esac; \
	echo "for the ls / setcomm / rmcomm / getcomm functions, add to ~/.zshrc:"; \
	echo "    source $$datadir/lsc.zsh"

uninstall:
	@bindir=$$(eval echo "$(BINDIR)"); \
	datadir=$$(eval echo "$(DATADIR)"); \
	rm -f "$$bindir/lsc" "$$datadir/lsc.zsh"; \
	rmdir "$$datadir" 2>/dev/null || true; \
	echo "removed $$bindir/lsc and $$datadir/lsc.zsh"

test:
	sh tests/run-tests.sh
