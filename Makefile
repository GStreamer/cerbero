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
	PYTHONPATH=$(PYTHONPATH):./test:./cerbero; trial test
	make check-format

coverage:
	rm -rf _trial_temp
	PYTHONPATH=$(PYTHONPATH):./test:./cerbero; trial --coverage test
	make show-coverage

show-coverage:
	python tools/show-coverage.py _trial_temp/coverage/cerbero.*
