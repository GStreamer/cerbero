import os
import re
import sys


class Presentation:

    def __init__(self, name, lines, covered):
        self.name = name
        self.lines = lines
        self.covered = covered

        if self.covered == 0:
            self.percent = 0
        else:
            self.percent = 100 * self.covered / float(self.lines)

    def show(self, maxlen=20):
        format = '%%-%ds  %%3d %%%%   (%%4d / %%4d)' % maxlen
        print(format % (self.name, self.percent, self.covered, self.lines))


class Coverage:

    def __init__(self):
        self.files = []
        self.total_lines = 0
        self.total_covered = 0

        # The python Trace class prints coverage results by prefixing
        # lines that got executed with a couple of spaces, the number
        # of times it has been executed and a colon. Uncovered lines
        # get prefixed with six angle brackets. Lines like comments
        # and blank lines just get indented.
        # This regexp will match executed and executable-but-not-covered lines.
        self.codeline_matcher = re.compile(r'^(>>>>>>)|(\s*\d+:)')

    def _strip_filename(self, filename):
        filename = os.path.basename(filename)
        if filename.endswith('.cover'):
            filename = filename[:-6]
        return filename

    def add_file(self, file):
        self.files.append(file)

    def show_results(self):
        if not hasattr(self, 'files'):
            print('No coverage data')
            return

        if self.files:
            self.maxlen = max([len(self._strip_filename(f)) for f in self.files])
        else:
            self.maxlen = 0

        print('Coverage report:')
        print('-' * (self.maxlen + 23))
        for file in self.files:
            self.show_one(file)
        print('-' * (self.maxlen + 23))

        p = Presentation('Total', self.total_lines, self.total_covered)
        p.show(self.maxlen)

    def show_one(self, filename):
        f = open(filename)
        # Grab all executables lines
        lines = [line for line in f.readlines()
                 if self.codeline_matcher.match(line)]

        # Find out which of them were not executed
        uncovered_lines = [line for line in lines
                                   if line.startswith('>>>>>>')]
        if not lines:
            return

        filename = self._strip_filename(filename)

        p = Presentation(filename,
                         len(lines),
                         len(lines) - len(uncovered_lines))
        p.show(self.maxlen)

        self.total_lines += p.lines
        self.total_covered += p.covered


def main(args):
    c = Coverage()
    files = args[1:]
    files.sort()
    for file in files:
        if 'flumotion.test' in file:
            continue
        if '__init__' in file:
            continue
        c.add_file(file)

    c.show_results()

if __name__ == '__main__':
    sys.exit(main(sys.argv))
