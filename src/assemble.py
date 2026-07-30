"""Inject the data payload into the page template."""
import os, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import paths


SITE = 'https://ethan-m2024.github.io/Hatchery-Insights/'


def share_description():
    """The sentence a link preview shows, written from the data rather than fixed.

    Social crawlers do not run JavaScript, so this cannot be filled in by the page.
    Deriving it here keeps the seasons it quotes honest as the record grows.
    """
    import json
    with paths.open_text(paths.PAYLOAD) as f:
        meta = json.load(f)['meta']
    seasons = meta.get('seasons') or []
    if not seasons:
        return ('Washington hatchery salmon and steelhead returns, parsed from WDFW '
                'reports and reconciled against their published totals.')
    a, b = seasons[0], meta.get('final_through') or seasons[-1]
    return (f'Every salmon and steelhead counted back to a Washington hatchery rack, '
            f'{a}\u2013{str(a + 1)[2:]} to {b}\u2013{str(b + 1)[2:]}. Parsed from WDFW\u2019s '
            f'PDF reports, reconciled against their own published totals, rebuilt daily.')


def main():
    tpl = open(paths.TEMPLATE, encoding='utf-8').read()
    data = open(paths.PAYLOAD, encoding='utf-8').read()
    assert '__DATA__' in tpl, 'the template has lost its __DATA__ placeholder'
    desc = share_description()
    for token, value in (('__DESC__', desc), ('__URL__', SITE)):
        assert token in tpl, f'the template has lost its {token} placeholder'
        tpl = tpl.replace(token, value.replace('"', '&quot;'))
    out = tpl.replace('__DATA__', data.replace('</', '<\\/'))
    os.makedirs(paths.DOCS, exist_ok=True)
    with open(paths.DASHBOARD, 'w', encoding='utf-8') as f:
        f.write(out)
    print(f'   dashboard written: {os.path.relpath(paths.DASHBOARD, paths.ROOT)} '
          f'({len(out) // 1024} KB)')
    return paths.DASHBOARD


if __name__ == '__main__':
    main()
