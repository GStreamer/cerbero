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
	pep8 cerbero -r
