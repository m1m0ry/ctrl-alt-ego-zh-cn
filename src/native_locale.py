"""Ctrl Alt Ego build22614084 native locale encoding and text rendering."""
import csv
import io
import re
import struct
import subprocess
import zlib

def _encoding(metadata):
    _, _, offset, size, data, _ = struct.unpack_from('<6I', metadata)
    literals = []
    for pos in range(offset, offset + size, 8):
        length, index = struct.unpack_from('<II', metadata, pos)
        literals.append(metadata[data + index:data + index + length].decode('utf-8'))
    anchor = literals.index('BEGIN LOCALIZATION Encoding all assets for language ')
    key, iv = [s.encode() for s in literals[anchor:anchor + 12]
               if re.fullmatch(r'[A-F0-9]{8}-[A-F0-9]{4}-[A-F0-9]{2}', s)]


    def aes(body, decrypt=False):
        return subprocess.run(['/usr/bin/openssl', 'enc', '-d' if decrypt else '-e', '-aes-128-cbc',
                               '-K', key.hex(), '-iv', iv.hex()], input=body,
                              capture_output=True, check=True).stdout

    return aes

def decode_native_locale(files, metadata):
    """Decode relative native-locale filenames from owned game resources."""
    aes = _encoding(metadata)
    return {name: body if name == '.locale.info' else zlib.decompress(aes(body, True), 31)
            for name, body in files.items()}


def render_native_locale(clear_files, entries, metadata, version='0.1.8'):
    """Return encoded zh-cn files; entries contain stable id/source/translation."""
    assert re.fullmatch(r'\d+\.\d+\.\d+', version)
    clear_files = dict(clear_files)
    translations = entries
    by_id = {row['id']: row for row in translations}
    assert len(by_id) == len(translations) == 5491
    aes = _encoding(metadata)
    used = set()
    table = list(csv.reader(io.StringIO(clear_files['translations.csv'].decode('utf-8-sig'), newline='')))
    plot_text = {}
    for row in table[1:]:
        ident = 'csv:' + row[0] + '/' + row[1]
        if ident in by_id:
            entry = by_id[ident]
            assert entry['source'] == row[3] and entry['translation'].strip()
            row[3] = entry['translation']
            used.add(ident)
        plot_text[row[0] + '/' + row[1]] = row[3]
    buffer = io.StringIO(newline='')
    csv.writer(buffer, lineterminator='\n').writerows(table)
    clear_files['translations.csv'] = buffer.getvalue().encode()
    for name, body in list(clear_files.items()):
        if name.startswith('Captions/'):
            line_break = '\r\n' if b'\r\n' in body else '\n'
            text = body.decode('utf-8-sig').replace('\r\n', '\n')
            def replace(match):
                cue, timing, source_text = match.group(1, 2, 3)
                ident = 'caption:' + name + ':' + cue
                if ident not in by_id:
                    return match.group()
                entry = by_id[ident]
                assert source_text == entry['source']
                used.add(ident)
                return cue + '\n' + timing + '\n' + entry['translation']
            text = re.sub(r'(?m)^(\d+)\n([^\n]*-->[^\n]*)\n(.*?)(?=\n\s*\n|\Z)', replace, text, flags=re.S)
            assert re.findall(r'(?m)^(\d+)\n([^\n]*-->[^\n]*)', text) == re.findall(r'(?m)^(\d+)\n([^\n]*-->[^\n]*)', body.decode('utf-8-sig').replace('\r\n','\n'))
            clear_files[name] = text.replace('\n', line_break).encode()
        elif name.startswith('Plot/'):
            lines = []
            for line in body.decode().splitlines(keepends=True):
                if line.startswith('#') or not line.strip():
                    lines.append(line)
                    continue
                parts = line.split('#')
                value = plot_text[parts[0]]
                assert '#' not in value and '\n' not in value and len(parts) == 6
                parts[1] = value
                lines.append('#'.join(parts))
            clear_files[name] = ''.join(lines).encode()
    assert used == set(by_id)
    font_map = clear_files['FontMap.txt'].decode()
    font_map += ('\n$Share Tech Mono,NotepadFont\n$a dripping marker,Muyao-Softbrush\n'
                 '$Just Another Hand,Muyao-Softbrush\n$WideCharacter/Begin,19968\n'
                 '$WideCharacter/End,195103\n$WideCharacter/Width,2.22\n')
    clear_files['FontMap.txt'] = font_map.encode()
    clear_files['.locale.info'] = ('display-name = \u7b80\u4f53\u4e2d\u6587\napi-codes = schinese\n'
                                  f'author = Community Chinese localization v{version}\n').encode()

    result = {}
    for name, body in clear_files.items():
        if name == '.locale.info':
            encoded = body
        else:
            compressor = zlib.compressobj(9, zlib.DEFLATED, 31)
            packed = compressor.compress(body) + compressor.flush() + b'\xef\xbb\xbf'
            encoded = aes(packed)
            assert zlib.decompress(aes(encoded, True), 31) == body
        result[name] = encoded
    return result
