"""Inject the data payload into the page template."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths


def main():
    tpl = open(paths.TEMPLATE, encoding='utf-8').read()
    data = open(paths.PAYLOAD, encoding='utf-8').read()
    assert '__DATA__' in tpl, 'the template has lost its __DATA__ placeholder'
    out = tpl.replace('__DATA__', data.replace('</', '<\\/'))
    os.makedirs(paths.DOCS, exist_ok=True)
    with open(paths.DASHBOARD, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'   dashboard written: {os.path.relpath(paths.DASHBOARD, paths.ROOT)} '
          f'({len(out) // 1024} KB)')
    return paths.DASHBOARD


if __name__ == '__main__':
    main()
