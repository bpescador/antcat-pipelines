#!/usr/bin/env python3
"""
extract_streamed_pdfs.py -- read the stream from stream_reference_pdfs.rb on stdin and write each PDF in it to
DIR, as the stream arrives.

Skips whatever Rails printed to stdout before the marker; accepts only plain files with a plain name (no
folders, no "..", no links), so nothing can land outside DIR; never overwrites a file that already exists with
other content (reports it instead). Prints a line per 100 files and a summary.

Usage (on the Mac; stream_reference_pdfs.rb has the whole command):
  ssh antcat '...rails runner tmp/stream_reference_pdfs.rb' 2> stream.log | python3 extract_streamed_pdfs.py DIR
"""
import os, sys, tarfile

MARKER = b'\n__ANTCAT_PDF_TAR_STREAM__\n'


class AfterMarker:
    """A read-only stream: stdin from just after MARKER."""

    def __init__(self, raw):
        self.raw, self.buf, self.skipped = raw, b'', 0
        while True:
            chunk = raw.read(1 << 16)
            if not chunk:
                sys.exit(f'no stream marker in the input ({self.skipped + len(self.buf)} bytes); see the stderr log')
            self.buf += chunk
            i = self.buf.find(MARKER)
            if i >= 0:
                self.skipped += i
                self.buf = self.buf[i + len(MARKER):]
                return
            keep = len(MARKER) - 1  # the marker may straddle two chunks
            self.skipped += max(0, len(self.buf) - keep)
            self.buf = self.buf[-keep:]

    def read(self, n=-1):
        if self.buf:
            out = self.buf if n < 0 else self.buf[:n]
            self.buf = self.buf[len(out):]
            return out
        return self.raw.read(n)


def main():
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    out = os.path.expanduser(sys.argv[1])
    os.makedirs(out, exist_ok=True)
    stream = AfterMarker(sys.stdin.buffer)
    if stream.skipped:
        print(f'skipped {stream.skipped} bytes printed before the stream (Rails boot output)', file=sys.stderr)
    written = refused = same = 0
    total = 0
    with tarfile.open(fileobj=stream, mode='r|') as tar:
        for m in tar:
            name = m.name
            if not m.isfile() or '/' in name or name in ('.', '..') or name.startswith('.'):
                print(f'REFUSED {name!r}: not a plain file name', file=sys.stderr)
                refused += 1
                continue
            data = tar.extractfile(m).read()
            path = os.path.join(out, name)
            if os.path.exists(path):
                if open(path, 'rb').read() == data:
                    same += 1
                    continue
                print(f'REFUSED {name}: a different file of that name exists', file=sys.stderr)
                refused += 1
                continue
            with open(path + '.part', 'wb') as f:
                f.write(data)
            os.replace(path + '.part', path)
            written += 1
            total += len(data)
            if written % 100 == 0:
                print(f'{written} files, {total / 1e9:.2f} GB', file=sys.stderr, flush=True)
    print(f'written {written}, already there {same}, refused {refused}; {total / 1e9:.2f} GB in {out}')


if __name__ == '__main__':
    main()
