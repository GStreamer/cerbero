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

check:
	PYTHONPATH=$(PYTHONPATH):./test:./cerbero; trial test
	find cerbero ! -regex cerbero/packages/debian.py -name \*.py | sort -u | xargs pep8 --repeat

coverage:
	rm -rf _trial_temp
	PYTHONPATH=$(PYTHONPATH):./test:./cerbero; trial --coverage test cerbero
	make show-coverage

show-coverage:
	python tools/show-coverage.py _trial_temp/coverage/cerbero.*
