"""Replace the main font data while retaining original symbol fallback."""
from pathlib import Path
import hashlib
import UnityPy


def patch_font_asset(source, font, output):
    """Use owned original sharedassets0 and an appropriately licensed font file."""
    source, font, output = Path(source), Path(font), Path(output)
    assert not output.exists()
    assert hashlib.sha256(source.read_bytes()).hexdigest() == '58de88a5d1b4baa9cf19b4a937e92423206edc40bd640447a31d4702c1b7cbfb'
    env = UnityPy.load(str(source))
    objects = {o.path_id: o for o in env.objects}
    before = {i: hashlib.sha256(o.get_raw_data()).hexdigest() for i, o in objects.items()}
    main = objects[1687].read_typetree()
    fallback = objects[1694].read_typetree()
    original = main['m_FontData']
    assert not fallback['m_FontData']
    main['m_FontData'] = list(font.read_bytes())
    main['m_FontNames'] += ['cae.NotepadFont Clone', 'cae.NotepadFont-Clone']
    main['m_FallbackFonts'] = [{'m_FileID': 0, 'm_PathID': 1694}]
    fallback['m_FontData'] = original
    fallback['m_FallbackFonts'] = []
    objects[1687].save_typetree(main)
    objects[1694].save_typetree(fallback)
    output.write_bytes(env.file.save())
    checked = UnityPy.load(str(output))
    changed = {o.path_id for o in checked.objects
               if hashlib.sha256(o.get_raw_data()).hexdigest() != before[o.path_id]}
    assert changed == {1687, 1694}
    return output
