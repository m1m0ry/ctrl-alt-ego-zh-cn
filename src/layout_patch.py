"""Native input-prompt layout correction for original build22614084."""
import hashlib
import struct

def digest(data):
    return hashlib.sha256(data).hexdigest()

def patch_native(original):
    assert digest(original) == '7a377c1d7a311d11c227256bfd409dc9008fd9b0a8a9c9cb8b3b36a8990bb480', 'unknown GameAssembly.dll build'
    coff = struct.unpack_from('<I', original, 0x3c)[0]
    assert original[coff:coff+4] == b'PE\0\0'
    assert struct.unpack_from('<H', original, coff+4)[0] == 0x8664
    optional = coff+24
    assert struct.unpack_from('<H', original, optional)[0] == 0x20b
    image_base = struct.unpack_from('<Q', original, optional+24)[0]
    section_start = optional + struct.unpack_from('<H', original, coff+20)[0]
    sections = []
    for i in range(struct.unpack_from('<H', original, coff+6)[0]):
        at = section_start+i*40
        size, rva, raw_size, raw = struct.unpack_from('<4I', original, at+8)
        sections.append((rva, raw_size, raw))
    def offset(va):
        for rva, raw_size, raw in sections:
            if rva <= va-image_base < rva+raw_size:
                return raw + va-image_base-rva
        raise ValueError('VA not backed by file')
    result = bytearray(original)
    changes = []
    def replace(va, expected, candidate, reason):
        assert len(expected) == len(candidate)
        at = offset(va)
        assert original[at:at+len(expected)] == expected, (hex(va), 'unexpected instruction')
        result[at:at+len(expected)] = candidate
        changes.append({'va': hex(va), 'file_offset': at, 'before': expected.hex(), 'after': candidate.hex(), 'reason': reason})
    # Static native ABI: RCX=String, DL=roundUp, R8=MethodInfo(null), EAX=int.
    replace(0x180d1be58, bytes.fromhex('33d2'), bytes.fromhex('b201'), 'Request roundUp=true for existing native width measurement')
    replace(0x180d1be5d, b'\xe8'+struct.pack('<i', 0x180416920-(0x180d1be5d+5)),
            b'\xe8'+struct.pack('<i', 0x180be3230-(0x180d1be5d+5)),
            'Use FontLocalizer.MeasureNumBackgroundCharactersNeeded instead of raw character count')
    # Change this instruction reference only, never the shared constant itself.
    assert struct.unpack_from('<f', original, offset(0x180e1d3a0))[0] == 1.0
    assert struct.unpack_from('<f', original, offset(0x180e1d3c0))[0] == 2.0
    instruction_end = 0x180d1bea2
    replace(0x180d1be9a, bytes.fromhex('f30f5c05')+struct.pack('<i', 0x180e1d3a0-instruction_end),
            bytes.fromhex('f30f5c05')+struct.pack('<i', 0x180e1d3c0-instruction_end),
            'Reserve one additional native character cell for wide controller glyphs, including Latin Ctrl')
    # The program panel places its two direction glyphs independently of MessagesUI.
    # Use the verified alignment gap after this method for a 10-byte leaf: only
    # volatile EAX/XMM0 change, with no stack frame or unwind entry required.
    panel_anchor = 0x180dd4514
    leaf = b'\xb8' + struct.pack('<i', -86) + bytes.fromhex('f30f2ac0c3')
    replace(panel_anchor, b'\xcc' * len(leaf), leaf,
            'Keep program-selection direction glyphs left of the CJK label')
    for call in (0x180dd3add, 0x180dd3b35):
        replace(call, b'\xe8' + struct.pack('<i', 0x180cd42f0 - (call + 5)),
                b'\xe8' + struct.pack('<i', panel_anchor - (call + 5)),
                'Program panel direction glyph anchor only; install glyph unchanged')
    # Give the details panel's short centred CJK Install/Confirm labels room
    # beside their glyphs; preserve vertical placement and the existing margin.
    # The program-list Install glyph uses another path unchanged.
    assert struct.unpack_from('<f', original, offset(0x180e1d38c))[0] == 0.5
    assert struct.unpack_from('<f', original, offset(0x180e4a010))[0] == 2.5
    for instruction in (0x180dcf23f, 0x180dcf843):
        end = instruction + 8
        replace(instruction, bytes.fromhex('f30f591d') + struct.pack('<i', 0x180e1d38c - end),
                bytes.fromhex('f30f591d') + struct.pack('<i', 0x180e4a010 - end),
                'Reserve centred CJK Install/Confirm glyph clearance in the details panel')
    allowed = {at+i for c in changes for at in [c['file_offset']] for i in range(len(bytes.fromhex(c['before'])))}
    assert len(result) == len(original)
    actual = [i for i, (a,b) in enumerate(zip(original,result)) if a != b]
    assert set(actual) <= allowed
    return bytes(result), {'original_sha256': digest(original), 'candidate_sha256': digest(result),
                           'size_bytes': len(result), 'instruction_sites': changes, 'changed_byte_count': len(actual)}
