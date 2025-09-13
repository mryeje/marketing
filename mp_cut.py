
# mp_cut.py
import argparse, os, re, sys
from moviepy.editor import VideoFileClip, TextClip, CompositeVideoClip
from moviepy.video.fx.all import crop
from moviepy.video.fx.resize import resize

def parse_size(s):
    m = re.match(r"^(\d+)x(\d+)$", s)
    if not m:
        raise argparse.ArgumentTypeError("Size must be like 1080x1920")
    return int(m.group(1)), int(m.group(2))

def pad_to(canvas_w, canvas_h, clip):
    # scale to fit inside canvas, then pad with black bars
    iw, ih = clip.w, clip.h
    scale = min(canvas_w / iw, canvas_h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    clip_resized = resize(clip, (new_w, new_h))
    # center on canvas
    from moviepy.video.VideoClip import ColorClip
    bg = ColorClip(size=(canvas_w, canvas_h), color=(0,0,0), duration=clip_resized.duration).set_fps(clip_resized.fps)
    return CompositeVideoClip([bg, clip_resized.set_position("center")]).set_audio(clip_resized.audio)

def crop_to(canvas_w, canvas_h, clip):
    # scale to fill canvas, then center-crop overflow
    iw, ih = clip.w, clip.h
    scale = max(canvas_w / iw, canvas_h / ih)
    new_w, new_h = int(iw * scale), int(ih * scale)
    clip_resized = resize(clip, (new_w, new_h))
    x1 = (clip_resized.w - canvas_w) // 2
    y1 = (clip_resized.h - canvas_h) // 2
    return crop(clip_resized, x1=x1, y1=y1, x2=x1+canvas_w, y2=y1+canvas_h)

def main():
    ap = argparse.ArgumentParser(description="Cut + reframe a clip with MoviePy")
    ap.add_argument("--src", required=True, help="Source video path")
    ap.add_argument("--start", required=True, help="Start time (HH:MM:SS or MM:SS)")
    ap.add_argument("--end", required=True, help="End time   (HH:MM:SS or MM:SS)")
    ap.add_argument("--out", required=True, help="Output path")
    ap.add_argument("--size", default="1080x1920", type=parse_size, help="Canvas size WxH (default 1080x1920)")
    ap.add_argument("--pad", action="store_true", help="Pad to fit (default crop-to-fill if not set)")
    ap.add_argument("--fps", type=int, default=30, help="Output FPS (default 30)")
    ap.add_argument("--crf", type=int, default=18, help="x264 quality (lower=better, default 18)")
    ap.add_argument("--srt", help="Optional SRT to burn in")
    args = ap.parse_args()

    start, end = args.start, args.end
    cw, ch = args.size

    base = VideoFileClip(args.src)
    sub = base.subclip(start, end)

    # Reframe
    outclip = pad_to(cw, ch, sub) if args.pad else crop_to(cw, ch, sub)
    outclip = outclip.set_fps(args.fps)

    # Optional hard-burn captions via moviepy TextClip (simple SRT parser)
    if args.srt:
        try:
            import pysrt
        except ImportError:
            sys.stderr.write("pysrt not installed; skipping SRT burn-in\n")
            pysrt = None
        if pysrt:
            subs = pysrt.open(args.srt)
            overlays = []
            for s in subs:
                t_start = s.start.ordinal/1000.0 - sub.start
                t_end = s.end.ordinal/1000.0 - sub.start
                if t_end <= 0 or t_start >= sub.duration: 
                    continue
                t_start = max(0, t_start); t_end = min(sub.duration, t_end)
                txt = TextClip(s.text.replace("\n"," "), fontsize=56, color="white", stroke_color="black", stroke_width=2, method="caption", size=(int(cw*0.9), None))
                overlays.append(txt.set_start(t_start).set_end(t_end).set_position(("center", int(ch*0.85))))
            if overlays:
                outclip = CompositeVideoClip([outclip, *overlays]).set_audio(outclip.audio)

    # Write
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    outclip.write_videofile(
        args.out,
        codec="libx264",
        audio_codec="aac",
        fps=args.fps,
        preset="veryfast",
        ffmpeg_params=["-crf", str(args.crf)]
    )

if __name__ == "__main__":
    main()
