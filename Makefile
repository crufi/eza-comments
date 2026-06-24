# comment: install/uninstall the lsc command and shell functions

# Override locations with e.g. `make install PREFIX=/usr/local` or
# `make install BINDIR=~/bin`. Defaults live under ~/.local, which needs no
# sudo. A leading ~ in an override is expanded (via eval echo) so it never
# lands on disk literally, regardless of the shell that invoked make.
PREFIX  ?= $(HOME)/.local
BINDIR  ?= $(PREFIX)/bin
DATADIR ?= $(PREFIX)/share/lsc
MANDIR  ?= $(PREFIX)/share/man/man1
SCRIPT  := lsc.py

.PHONY: install uninstall test readme man

install:
	@bindir=$$(eval echo "$(BINDIR)"); \
	datadir=$$(eval echo "$(DATADIR)"); \
	mandir=$$(eval echo "$(MANDIR)"); \
	mkdir -p "$$bindir" "$$datadir"; \
	install -m 755 "$(SCRIPT)" "$$bindir/lsc"; \
	install -m 644 lsc.sh "$$datadir/lsc.sh"; \
	echo "installed $$bindir/lsc"; \
	echo "installed $$datadir/lsc.sh"; \
	if [ -f man/lsc.1 ]; then mkdir -p "$$mandir"; install -m 644 man/lsc.1 "$$mandir/lsc.1"; echo "installed $$mandir/lsc.1"; fi; \
	rp=$$(cd "$$bindir" 2>/dev/null && pwd -P); \
	: "rp is now bindir with symlinks resolved, so a synced ~/tools -> iCloud" \
	  "symlink still matches a PATH entry written in its resolved form"; \
	case ":$$PATH:" in \
	  *":$$bindir:"*|*":$$rp:"*) ;; \
	  *) echo "note: $$bindir is not on your PATH; add it to use 'lsc'";; \
	esac; \
	echo "for the setcomm/rmcomm/getcomm helper functions, add to your shell rc (~/.bashrc or ~/.zshrc):"; \
	echo "    source $$datadir/lsc.sh"

uninstall:
	@bindir=$$(eval echo "$(BINDIR)"); \
	datadir=$$(eval echo "$(DATADIR)"); \
	mandir=$$(eval echo "$(MANDIR)"); \
	rm -f "$$bindir/lsc" "$$datadir/lsc.sh" "$$mandir/lsc.1"; \
	rmdir "$$datadir" 2>/dev/null || true; \
	echo "removed $$bindir/lsc, $$datadir/lsc.sh, $$mandir/lsc.1"

test:
	sh tests/run-tests.sh

# regenerate the <!-- begin help -->...<!-- end help --> block in the README
# from `lsc --help`, so the docstring is the single source for the flag list.
readme:
	@awk -v cmd='python3 lsc.py --help' '/<!-- begin help -->/{print; print "```"; while((cmd|getline l)>0)print l; close(cmd); print "```"; s=1; next} /<!-- end help -->/{s=0} !s' README.md > README.tmp && mv README.tmp README.md
	@echo "regenerated README help block from lsc --help"

# generate a man page from the same --help (needs help2man: brew install help2man)
man:
	@command -v help2man >/dev/null 2>&1 || { echo "need help2man (brew install help2man)"; exit 1; }
	@mkdir -p man
	help2man -N -o man/lsc.1 "python3 lsc.py"
	@echo "wrote man/lsc.1 -- commit it to ship the man page"
