#!/usr/bin/env python3
"""
Normalize incoming recipe JSON into canonical form expected by the renderer.
This variant aggressively adds aliases and also propagates highlight/caption styles
into instruction-level 'effects' and item-level 'effects'/'background' so renderers
that expect those fields will receive them.

Usage:
  python recipe_normalizer.py input.json output_normalized.json
"""
import json
import re
import sys
from pathlib import Path

COLOR_MAP = {
    "white": "#ffffff", "black": "#000000", "yellow": "#ffff00",
    "dark_green": "#006400", "dark_blue": "#00008b", "dark_red": "#8b0000",
    "green": "#008040"
}

def parse_hms_ms(s):
    if s is None:
        return None
    s = str(s).strip()
    m = re.match(r"^(?:(\d+):)?(\d{1,2}):(\d{1,2})(?:[.,](\d{1,3}))?$", s)
    if not m:
        try:
            return float(s)
        except:
            return None
    h = int(m.group(1) or 0)
    mm = int(m.group(2))
    ss = int(m.group(3))
    ms = int((m.group(4) or "0").ljust(3, "0"))
    return h*3600 + mm*60 + ss + ms/1000.0

def ensure_hex(color):
    if color is None:
        return None
    color = str(color).strip()
    if color.startswith("#"):
        return color.lower()
    return COLOR_MAP.get(color.lower(), color)

def make_background_aliases(instr, value):
    if value:
        instr['background'] = value
        instr['background_color'] = value
        instr['bg_color'] = value
        instr['bg'] = value
        instr['box_color'] = value
    return instr

def ensure_effects_field(obj):
    # ensure both singular 'effect' and list 'effects' are present in useful forms
    if 'effects' not in obj and 'effect' in obj:
        effv = obj.get('effect')
        if isinstance(effv, (list, tuple)):
            obj['effects'] = list(effv)
        else:
            if isinstance(effv, str) and ',' in effv:
                obj['effects'] = [e.strip() for e in effv.split(',') if e.strip()]
            else:
                obj['effects'] = [effv]
    if 'effect' not in obj and 'effects' in obj:
        effs = obj.get('effects') or []
        if isinstance(effs, (list, tuple)) and effs:
            obj['effect'] = effs[0]
        else:
            obj['effect'] = effs
    return obj

def canonicalize_overlay_item(item, clip_start=0.0):
    ci = {}
    ci['text'] = item.get('text') or item.get('label') or ""
    start = item.get('start') or item.get('from')
    end = item.get('end') or item.get('to')
    if isinstance(start, str):
        start_num = parse_hms_ms(start)
    else:
        start_num = start
    if isinstance(end, str):
        end_num = parse_hms_ms(end)
    else:
        end_num = end
    if start_num is not None and clip_start is not None and start_num >= clip_start + 0.001:
        start_num = max(0.0, start_num - clip_start)
    if end_num is not None and clip_start is not None and end_num >= clip_start + 0.001:
        end_num = max(0.0, end_num - clip_start)
    ci['start'] = float(start_num) if start_num is not None else 0.5
    ci['end'] = float(end_num) if end_num is not None else ci['start'] + 4.0

    for k in ('placement','font','size','style','effect','effects','color','background','timing'):
        v = item.get(k)
        if v is not None:
            if k in ('color','background'):
                v = ensure_hex(v)
            ci[k if k != 'effect' else 'effect'] = v

    # normalize effects/ effect aliasing
    ensure_effects_field(ci)

    # background aliases and color alias
    bg = ci.get('background')
    if bg:
        ci['background_color'] = bg
        ci['bg'] = bg
    if 'color' in ci:
        ci['text_color'] = ci['color']

    return ci

def normalize_clip(clip):
    start = clip.get('start')
    end = clip.get('end')
    if isinstance(start, str): start = parse_hms_ms(start)
    if isinstance(end, str): end = parse_hms_ms(end)
    if start is None: start = 0.0
    if end is None and clip.get('clip_duration') is not None:
        end = start + float(clip['clip_duration'])
    clip['start'] = float(start)
    clip['end'] = float(end) if end is not None else float(start)

    srt = []
    if 'srt_for_clip' in clip and isinstance(clip['srt_for_clip'], list):
        for s in clip['srt_for_clip']:
            srt.append({
                'start': float(s.get('start',0.0)),
                'end': float(s.get('end',0.0)),
                'text': s.get('text','')
            })
    if 'subtitles' in clip and isinstance(clip['subtitles'], list):
        for s in clip['subtitles']:
            st = parse_hms_ms(s.get('from')) or 0.0
            et = parse_hms_ms(s.get('to')) or st
            st_rel = max(0.0, st - clip['start'])
            et_rel = max(st_rel, et - clip['start'])
            srt.append({'start': float(st_rel), 'end': float(et_rel), 'text': s.get('text','')})
    if srt:
        clip['srt_for_clip'] = srt

    overlay_items = []
    oi = clip.get('overlay_instructions', {}) or {}
    if isinstance(oi, dict):
        # normalize colors/effects and create aliases
        if 'color' in oi:
            oi['color'] = ensure_hex(oi['color'])
        if 'background' in oi:
            oi['background'] = ensure_hex(oi['background'])
        # convert effect -> effects if needed
        if 'effects' not in oi and 'effect' in oi:
            effv = oi.pop('effect')
            if isinstance(effv, (list, tuple)):
                oi['effects'] = list(effv)
            else:
                if isinstance(effv, str) and ',' in effv:
                    oi['effects'] = [e.strip() for e in effv.split(',') if e.strip()]
                else:
                    oi['effects'] = [effv]
        ensure_effects_field(oi)
        nested = oi.get('overlay_text') or []
        if isinstance(nested, list):
            for it in nested:
                overlay_items.append(canonicalize_overlay_item(it, clip_start=clip['start']))
        # aliases for instruction level backgrounds etc.
        oi = make_background_aliases(oi, oi.get('background') or oi.get('bg') or oi.get('background_color'))
        clip['overlay_instructions'] = oi

    flat = clip.get('overlay_text') or []
    if isinstance(flat, list):
        for it in flat:
            overlay_items.append(canonicalize_overlay_item(it, clip_start=clip['start']))

    if overlay_items:
        # dedupe
        seen = set()
        deduped = []
        for it in overlay_items:
            key = (it.get('text',''), round(it.get('start',0.0),3), round(it.get('end',0.0),3))
            if key not in seen:
                seen.add(key)
                deduped.append(it)

        # write both places and set aliases on each item
        clip['overlay_text'] = deduped[:]
        if 'overlay_instructions' not in clip or not isinstance(clip['overlay_instructions'], dict):
            clip['overlay_instructions'] = {}
        clip['overlay_instructions'].setdefault('overlay_text', [dict(x) for x in deduped[:]])

        # ensure each overlay_text item contains background & bg aliases if any
        instr_bg = clip['overlay_instructions'].get('background') or clip['overlay_instructions'].get('bg') or clip['overlay_instructions'].get('background_color')
        # if any item defines a background, use that to populate instruction background (prefer first non-null)
        if not instr_bg:
            for it in deduped:
                if it.get('background'):
                    instr_bg = it['background']
                    break
        if instr_bg:
            clip['overlay_instructions'] = make_background_aliases(clip['overlay_instructions'], instr_bg)

        # ensure instruction-level effects are present if items include them or highlight_style exists
        # gather item-level effects
        effs = []
        for it in deduped:
            if 'effects' in it:
                for e in it['effects']:
                    if e and e not in effs:
                        effs.append(e)
            elif it.get('effect'):
                v = it.get('effect')
                if isinstance(v, str) and v not in effs:
                    effs.append(v)
        # also look for highlight_style in instruction and caption/highlight styles
        hstyle = clip['overlay_instructions'].get('highlight_style') or {}
        # normalize highlight_style keys
        if isinstance(hstyle, dict):
            # if highlight_style.effect exists, make sure it is captured
            h_eff = hstyle.get('effect') or (hstyle.get('effects') and (hstyle.get('effects')[0] if isinstance(hstyle.get('effects'), list) and hstyle.get('effects') else None))
            if h_eff and h_eff not in effs:
                effs.append(h_eff)
            # also ensure highlight_style color/background normalized
            if 'color' in hstyle:
                hstyle['color'] = ensure_hex(hstyle['color'])
                clip['overlay_instructions']['highlight_style']['color'] = hstyle['color']
            if 'background' in hstyle:
                clip['overlay_instructions']['highlight_style']['background'] = ensure_hex(hstyle['background'])
            # return normalized highlight_style into instructions
            clip['overlay_instructions']['highlight_style'] = hstyle

        # If instruction-level effects are missing but we've gathered some, set them
        if effs and 'effects' not in clip['overlay_instructions']:
            clip['overlay_instructions']['effects'] = effs[:]
        else:
            # ensure existing instruction effects normalized
            if 'effects' in clip['overlay_instructions']:
                ensure_effects_field(clip['overlay_instructions'])

        # Now, propagate instruction effects into item-level effects where missing
        instr_effects = clip['overlay_instructions'].get('effects') or []
        # normalize to list of non-empty strings
        instr_effects = [e for e in instr_effects if e]
        for it in clip['overlay_text']:
            # ensure item-level has effects if missing
            if not it.get('effects') and not it.get('effect') and instr_effects:
                it['effects'] = instr_effects[:]
                it['effect'] = instr_effects[0] if instr_effects else None
            else:
                # normalize if item has singular effect
                ensure_effects_field(it)
            # ensure background alias present on items (from instruction bg if missing)
            if not it.get('background') and instr_bg:
                it['background'] = instr_bg
                it['bg'] = instr_bg
            if it.get('color'):
                it['text_color'] = it['color']

        # final aliasing on instruction level
        clip['overlay_instructions'] = make_background_aliases(clip['overlay_instructions'], clip['overlay_instructions'].get('background') or clip['overlay_instructions'].get('bg') or clip['overlay_instructions'].get('background_color'))
        ensure_effects_field(clip['overlay_instructions'])

    return clip

def normalize_recipe(recipe_payload):
    if 'recipe' in recipe_payload and isinstance(recipe_payload['recipe'], dict):
        recipe = recipe_payload['recipe']
    else:
        recipe = recipe_payload

    clips = recipe.get('clips', []) or []
    for i, c in enumerate(clips):
        clips[i] = normalize_clip(c)
    recipe['clips'] = clips
    return {'recipe': recipe}

def main():
    if len(sys.argv) < 3:
        print("Usage: recipe_normalizer.py input.json output_normalized.json", file=sys.stderr)
        sys.exit(1)
    inarg = sys.argv[1]
    outarg = sys.argv[2]
    if inarg == "-":
        data = json.load(sys.stdin)
    else:
        data = json.loads(Path(inarg).read_text(encoding='utf-8'))
    norm = normalize_recipe(data)
    if outarg == "-":
        json.dump(norm, sys.stdout, ensure_ascii=False, indent=2)
    else:
        Path(outarg).write_text(json.dumps(norm, ensure_ascii=False, indent=2), encoding='utf-8')
        print("Wrote normalized recipe to", outarg, file=sys.stderr)

if __name__ == "__main__":
    main()