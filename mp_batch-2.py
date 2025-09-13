import sys
from pathlib import Path
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import ColorClip

# Try importing margin / Margin depending on MoviePy version
try:
    from moviepy.video.fx.margin import margin as MarginFunc
except ImportError:
    try:
        from moviepy.video.fx.margin import Margin as MarginFunc
    except ImportError:
        raise ImportError("Could not find margin/Margin in moviepy. Check your MoviePy installation.")

def add_margin(clip, top=0, bottom=0, left=0, right=0, color=(0,0,0)):
    w, h = clip.size
    new_w = w + left + right
    new_h = h + top + bottom
    # put clip on a bigger color background
    return clip.on_color(size=(new_w, new_h), color=color, pos=(left, top))

def process_clips(json_file):
    import json
    
    with open(json_file, "r", encoding="utf-8") as f:
        clips_data = json.load(f)
    
    video_path = Path(clips_data["src"])
    if not video_path.exists():
        raise FileNotFoundError(f"Source video not found: {video_path}")
    
    video = VideoFileClip(str(video_path))
    output_dir = Path("clips")
    output_dir.mkdir(exist_ok=True)
    
    for idx, item in enumerate(clips_data["clips"], start=1):
        start = item["start"]
        end = item["end"]
        label = item["label"]
        
        print(f"[{idx}/{len(clips_data['clips'])}] Cutting {start} -> {end} -> {output_dir / (item['id'] + '.mp4')}")
        
        # CORRECTED: Changed subclipped() to subclip()
        subclip = video.subclip(start, end)
        
        # FIXED: Use resize effect properly - check import at runtime
        try:
            from moviepy.video.fx.resize import resize
            # Newer MoviePy versions
            subclip = subclip.fx(resize, height=1920)
        except ImportError:
            # Fallback for older versions - calculate new width maintaining aspect ratio
            aspect_ratio = subclip.w / subclip.h
            new_width = int(1920 * aspect_ratio)
            subclip = subclip.resize((new_width, 1920))
        
        if subclip.w < 1080:
            pad_left = (1080 - subclip.w) // 2
            pad_right = 1080 - subclip.w - pad_left
            subclip = MarginFunc(subclip, left=pad_left, right=pad_right, color=(0, 0, 0))
        
        subclip = subclip.set_fps(30)
        
        out_file = output_dir / f"{item['id']}_{label.replace(' ', '_').replace('—','-')}.mp4"
        subclip.write_videofile(
            str(out_file), 
            codec="libx264", 
            preset="slow",  # Better quality vs speed tradeoff
            bitrate="8000k",  # Much higher video bitrate
            audio_codec="aac", 
            audio_bitrate="192k",  # Higher audio bitrate
            ffmpeg_params=["-crf", "18"]  # Add CRF for better quality control
        )
        
        # Clean up the subclip to free resources
        subclip.close()
    
    # Clean up the main video clip
    video.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python mp_batch.py clips_recipe.json")
        sys.exit(1)
    
    process_clips(sys.argv[1])