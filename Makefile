ifdef PREFIX
  PREFIX_ARGS='--prefix=$(PREFIX)'
else
  PREFIX_ARGS=
endif

all:
	python setup.py build

install:
	python setup.py install $(PREFIX_ARGS)

dist-tarball:
	python setup.py sdist --formats=bztar

format:
	ruff format .

check-format:
	ruff check .

check:
	CERBERO_UNINSTALLED=1 PYTHONPATH=$(PYTHONPATH):./test:./cerbero trial3 test
	make check-format

coverage:
	rm -rf _trial_temp
	CERBERO_UNINSTALLED=1 PYTHONPATH=$(PYTHONPATH):./test:./cerbero trial3 --coverage test
	make show-coverage

show-coverage:
	python tools/show-coverage.py _trial_temp/coverage/cerbero.*
