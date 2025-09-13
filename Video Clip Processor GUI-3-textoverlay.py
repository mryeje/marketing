import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import json
import sys
from pathlib import Path
from moviepy.video.io.VideoFileClip import VideoFileClip
import queue
import os
from PIL import Image, ImageDraw, ImageFont
from moviepy.editor import ImageClip, CompositeVideoClip


# Try importing margin / Margin depending on MoviePy version
try:
    from moviepy.video.fx.margin import margin as MarginFunc
except ImportError:
    try:
        from moviepy.video.fx.margin import Margin as MarginFunc
    except ImportError:
        MarginFunc = None  # fallback handled in code


class VideoClipProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Clip Processor")
        self.root.geometry("900x740")

        # Queue for thread communication
        self.message_queue = queue.Queue()

        # Variables
        self.json_file_path = tk.StringVar()
        self.output_folder = tk.StringVar(value=str(Path.cwd() / "clips"))
        self.video_format = tk.StringVar(value="1080x1920")  # Short-form default
        self.fps = tk.IntVar(value=30)
        self.quality_preset = tk.StringVar(value="medium")
        self.bitrate = tk.StringVar(value="6000k")
        self.crf = tk.IntVar(value=20)
        self.include_audio = tk.BooleanVar(value=True)
        self.audio_bitrate = tk.StringVar(value="192k")
        self.processing = False

        # --- Text Overlay Options ---
        self.add_text_overlay = tk.BooleanVar(value=False)
        self.overlay_text = tk.StringVar()  # supports placeholders {label}, {id}, {start}, {end}
        self.overlay_position = tk.StringVar(value="bottom")
        self.overlay_fontsize = tk.IntVar(value=48)
        self.overlay_color = tk.StringVar(value="white")

        # --- Thumbnail Options ---
        self.generate_thumbnails = tk.BooleanVar(value=False)
        self.thumb_time = tk.StringVar(value="middle")
        self.thumb_custom_time = tk.StringVar(value="")
        self.thumb_size = tk.StringVar(value="1920x1080")

        self.create_widgets()
        self.check_queue()

    def create_widgets(self):
        # Main frame
        main_frame = ttk.Frame(self.root, padding="10")
        main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))

        # Configure grid weights
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        main_frame.columnconfigure(1, weight=1)
        main_frame.columnconfigure(2, weight=0)
        main_frame.columnconfigure(3, weight=0)
        main_frame.columnconfigure(4, weight=0)

        row = 0

        # JSON file selection
        ttk.Label(main_frame, text="Clips Recipe (JSON):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.json_file_path, width=60).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5), columnspan=2)
        ttk.Button(main_frame, text="Browse", command=self.browse_json_file).grid(row=row, column=3, padx=(5, 0))
        ttk.Button(main_frame, text="Paste JSON", command=self.open_json_paste_dialog).grid(row=row, column=4, padx=(5, 0))
        row += 1

        # Output folder selection
        ttk.Label(main_frame, text="Output Folder:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_folder, width=60).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5), columnspan=2)
        ttk.Button(main_frame, text="Browse", command=self.browse_output_folder).grid(row=row, column=3, padx=(5, 0))
        row += 1

        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=10)
        row += 1

        # Video format options
        format_frame = ttk.LabelFrame(main_frame, text="Video Format", padding="5")
        format_frame.grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=5)
        format_frame.columnconfigure(1, weight=1)

        ttk.Radiobutton(format_frame, text="Short-form (1080x1920)", variable=self.video_format, value="1080x1920").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(format_frame, text="Landscape (1920x1080)", variable=self.video_format, value="1920x1080").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(format_frame, text="Square (1080x1080)", variable=self.video_format, value="1080x1080").grid(row=0, column=2, sticky=tk.W)
        ttk.Radiobutton(format_frame, text="Original", variable=self.video_format, value="original").grid(row=1, column=0, sticky=tk.W)
        row += 1

        # Quality settings
        quality_frame = ttk.LabelFrame(main_frame, text="Quality Settings", padding="5")
        quality_frame.grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=5)
        quality_frame.columnconfigure(1, weight=1)
        quality_frame.columnconfigure(3, weight=1)

        # FPS
        ttk.Label(quality_frame, text="FPS:").grid(row=0, column=0, sticky=tk.W, padx=(0, 5))
        fps_combo = ttk.Combobox(quality_frame, textvariable=self.fps, values=[24, 30, 60], width=10, state="readonly")
        fps_combo.grid(row=0, column=1, sticky=tk.W, padx=(0, 20))

        # Preset
        ttk.Label(quality_frame, text="Preset:").grid(row=0, column=2, sticky=tk.W, padx=(0, 5))
        preset_combo = ttk.Combobox(quality_frame, textvariable=self.quality_preset,
                                   values=["ultrafast", "superfast", "veryfast", "faster", "fast", "medium", "slow", "slower", "veryslow"],
                                   width=12, state="readonly")
        preset_combo.grid(row=0, column=3, sticky=tk.W)

        # Bitrate
        ttk.Label(quality_frame, text="Bitrate:").grid(row=1, column=0, sticky=tk.W, padx=(0, 5))
        bitrate_combo = ttk.Combobox(quality_frame, textvariable=self.bitrate,
                                    values=["2000k", "4000k", "6000k", "8000k", "10000k"],
                                    width=10)
        bitrate_combo.grid(row=1, column=1, sticky=tk.W, padx=(0, 20))

        # CRF
        ttk.Label(quality_frame, text="CRF:").grid(row=1, column=2, sticky=tk.W, padx=(0, 5))
        crf_spin = ttk.Spinbox(quality_frame, from_=18, to=28, textvariable=self.crf, width=10)
        crf_spin.grid(row=1, column=3, sticky=tk.W)
        row += 1

        # Audio settings
        audio_frame = ttk.LabelFrame(main_frame, text="Audio Settings", padding="5")
        audio_frame.grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=5)
        audio_frame.columnconfigure(2, weight=1)

        ttk.Checkbutton(audio_frame, text="Include Audio", variable=self.include_audio).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(audio_frame, text="Audio Bitrate:").grid(row=0, column=1, sticky=tk.W, padx=(20, 5))
        audio_bitrate_combo = ttk.Combobox(audio_frame, textvariable=self.audio_bitrate,
                                          values=["128k", "192k", "256k", "320k"],
                                          width=10)
        audio_bitrate_combo.grid(row=0, column=2, sticky=tk.W)
        row += 1

        # Text Overlay section
        overlay_frame = ttk.LabelFrame(main_frame, text="Text Overlay", padding="5")
        overlay_frame.grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=5)
        overlay_frame.columnconfigure(1, weight=1)
        ttk.Checkbutton(overlay_frame, text="Add Text Overlay", variable=self.add_text_overlay).grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Label(overlay_frame, text="Text:").grid(row=0, column=1, sticky=tk.W)
        ttk.Entry(overlay_frame, textvariable=self.overlay_text, width=50).grid(row=0, column=2, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(overlay_frame, text="Show Sample", command=self._overlay_sample).grid(row=0, column=3, padx=(5, 0))

        ttk.Label(overlay_frame, text="Position:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        ttk.Combobox(overlay_frame, textvariable=self.overlay_position,
                     values=["top", "center", "bottom", "top-left", "top-right", "bottom-left", "bottom-right"],
                     width=15, state="readonly").grid(row=1, column=1, sticky=tk.W, pady=(5,0))

        ttk.Label(overlay_frame, text="Font Size:").grid(row=1, column=2, sticky=tk.W, pady=(5,0))
        ttk.Spinbox(overlay_frame, from_=20, to=120, textvariable=self.overlay_fontsize, width=8).grid(row=1, column=3, sticky=tk.W, pady=(5,0))

        ttk.Label(overlay_frame, text="Color:").grid(row=2, column=0, sticky=tk.W, pady=(5,0))
        ttk.Combobox(overlay_frame, textvariable=self.overlay_color, values=["white", "black", "red", "green", "blue", "yellow", "cyan", "magenta"], width=12, state="readonly").grid(row=2, column=1, sticky=tk.W, pady=(5,0))
        row += 1

        # Thumbnail Generation section
        thumb_frame = ttk.LabelFrame(main_frame, text="Thumbnail Generation", padding="5")
        thumb_frame.grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=5)
        thumb_frame.columnconfigure(1, weight=1)

        ttk.Checkbutton(thumb_frame, text="Generate Thumbnails", variable=self.generate_thumbnails).grid(row=0, column=0, sticky=tk.W, padx=(0, 10))
        ttk.Label(thumb_frame, text="Capture Time:").grid(row=0, column=1, sticky=tk.W)
        ttk.Combobox(thumb_frame, textvariable=self.thumb_time, values=["start", "middle", "end", "25%", "75%", "custom"], width=12, state="readonly").grid(row=0, column=2, sticky=tk.W)
        ttk.Entry(thumb_frame, textvariable=self.thumb_custom_time, width=10).grid(row=0, column=3, sticky=tk.W, padx=(5,0))

        ttk.Label(thumb_frame, text="Size:").grid(row=1, column=0, sticky=tk.W, pady=(5,0))
        ttk.Combobox(thumb_frame, textvariable=self.thumb_size, values=["1920x1080", "1280x720", "1080x1080", "640x360"], width=12, state="readonly").grid(row=1, column=1, sticky=tk.W, pady=(5,0))
        row += 1

        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=10)
        row += 1

        # Progress bar
        self.progress_var = tk.StringVar(value="Ready to process")
        ttk.Label(main_frame, textvariable=self.progress_var).grid(row=row, column=0, columnspan=5, sticky=tk.W)
        row += 1

        self.progress_bar = ttk.Progressbar(main_frame, mode='determinate')
        self.progress_bar.grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E), pady=5)
        row += 1

        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=5, pady=10)

        self.process_button = ttk.Button(button_frame, text="Process Clips", command=self.start_processing)
        self.process_button.pack(side=tk.LEFT, padx=(0, 10))

        ttk.Button(button_frame, text="Open Output Folder", command=self.open_output_folder).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT)
        row += 1

        # Log area
        ttk.Label(main_frame, text="Processing Log:").grid(row=row, column=0, sticky=tk.W, pady=(10, 0))
        row += 1

        self.log_text = scrolledtext.ScrolledText(main_frame, height=12, width=100)
        self.log_text.grid(row=row, column=0, columnspan=5, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        main_frame.rowconfigure(row, weight=1)

    # --- UI Helpers (same as before) ---
    def _overlay_sample(self):
        sample = "Clip: {label} ({start}s - {end}s)"
        self.overlay_text.set(sample)
        messagebox.showinfo("Sample Text", f"Sample overlay text inserted:\n\n{sample}")

    def browse_json_file(self):
        filename = filedialog.askopenfilename(
            title="Select Clips Recipe JSON File",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if filename:
            self.json_file_path.set(filename)

    def browse_output_folder(self):
        folder = filedialog.askdirectory(title="Select Output Folder")
        if folder:
            self.output_folder.set(folder)

    def open_output_folder(self):
        output_path = Path(self.output_folder.get())
        if output_path.exists():
            if sys.platform == "win32":
                os.startfile(str(output_path))
            elif sys.platform == "darwin":
                os.system(f"open '{output_path}'")
            else:
                os.system(f"xdg-open '{output_path}'")
        else:
            messagebox.showwarning("Warning", "Output folder doesn't exist yet.")

    def clear_log(self):
        self.log_text.delete(1.0, tk.END)

    def log_message(self, message):
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()

    def update_progress(self, current, total, message=""):
        if total > 0:
            progress_percent = (current / total) * 100
            self.progress_bar['value'] = progress_percent
        status = f"Processing {current}/{total}"
        if message:
            status += f" - {message}"
        self.progress_var.set(status)
        self.root.update_idletasks()

    # --- Processing control (unchanged except overlay call) ---
    def start_processing(self):
        if self.processing:
            return
        if not self.json_file_path.get():
            messagebox.showerror("Error", "Please select a JSON file or paste JSON.")
            return
        if not Path(self.json_file_path.get()).exists():
            messagebox.showerror("Error", "JSON file not found.")
            return
        output_path = Path(self.output_folder.get())
        output_path.mkdir(parents=True, exist_ok=True)
        self.processing = True
        self.process_button.config(text="Processing...", state="disabled")
        thread = threading.Thread(target=self.process_clips_thread)
        thread.daemon = True
        thread.start()

    def check_queue(self):
        try:
            while True:
                message_type, data = self.message_queue.get_nowait()
                if message_type == "log":
                    self.log_message(data)
                elif message_type == "progress":
                    current, total, msg = data
                    self.update_progress(current, total, msg)
                elif message_type == "done":
                    self.processing = False
                    self.process_button.config(text="Process Clips", state="normal")
                    self.progress_var.set("Processing complete!")
                    success, total = data
                    messagebox.showinfo("Complete", f"Processing finished!\nSuccessfully processed {success}/{total} clips.")
                elif message_type == "error":
                    self.processing = False
                    self.process_button.config(text="Process Clips", state="normal")
                    self.progress_var.set("Error occurred")
                    messagebox.showerror("Error", f"Processing failed: {data}")
        except queue.Empty:
            pass
        self.root.after(100, self.check_queue)

    def process_clips_thread(self):
        try:
            with open(self.json_file_path.get(), "r", encoding="utf-8") as f:
                clips_data = json.load(f)
            if "src" not in clips_data:
                self.message_queue.put(("error", "JSON missing required field 'src'"))
                return
            if "clips" not in clips_data or not isinstance(clips_data["clips"], list):
                self.message_queue.put(("error", "JSON missing required array 'clips'"))
                return
            video_path = Path(clips_data["src"])
            if not video_path.exists():
                self.message_queue.put(("error", f"Source video not found: {video_path}"))
                return
            self.message_queue.put(("log", f"Loading video: {video_path}"))
            video = VideoFileClip(str(video_path))
            output_dir = Path(self.output_folder.get())
            output_dir.mkdir(exist_ok=True)
            total_clips = len(clips_data["clips"])
            success_count = 0
            for idx, item in enumerate(clips_data["clips"], start=1):
                for field in ("id", "start", "end", "label"):
                    if field not in item:
                        self.message_queue.put(("log", f"Skipping clip {idx}: missing required field '{field}'"))
                        continue
                start = item["start"]; end = item["end"]; label = item["label"]
                self.message_queue.put(("progress", (idx, total_clips, f"Cutting {item.get('id','?')}")))
                self.message_queue.put(("log", f"[{idx}/{total_clips}] Processing {item.get('id','?')}: {start} -> {end}"))
                try:
                    subclip = video.subclip(start, end)
                    subclip = self.apply_video_format(subclip)
                    subclip = subclip.set_fps(self.fps.get())
                    subclip = self.apply_text_overlay(subclip, item)
                    safe_label = label.replace(' ', '_').replace('—', '-').replace('/', '_').replace('\\', '_')
                    out_file = output_dir / f"{item['id']}_{safe_label}.mp4"
                    if self.generate_thumbnails.get():
                        try:
                            self.generate_thumbnail(subclip, item, output_dir)
                        except Exception as e:
                            self.message_queue.put(("log", f"Thumbnail failed for {item['id']}: {str(e)}"))
                    self.write_video_file(subclip, out_file, item['id'])
                    subclip.close()
                    success_count += 1
                except Exception as e:
                    self.message_queue.put(("log", f"Error processing {item.get('id','?')}: {str(e)}"))
                    continue
            video.close()
            self.message_queue.put(("done", (success_count, total_clips)))
        except Exception as e:
            self.message_queue.put(("error", str(e)))

    # --- Video helpers (same as before, unchanged) ---
    def apply_video_format(self, clip):
        format_choice = self.video_format.get()
        if format_choice == "original":
            return clip
        target_w, target_h = map(int, format_choice.split('x'))
        try:
            from moviepy.video.fx.resize import resize
            if format_choice == "1080x1920":
                clip = clip.fx(resize, height=target_h)
            elif format_choice == "1920x1080":
                clip = clip.fx(resize, width=target_w)
            else:
                if clip.w > clip.h:
                    clip = clip.fx(resize, width=target_w)
                else:
                    clip = clip.fx(resize, height=target_h)
        except Exception:
            pass
        if clip.w != target_w or clip.h != target_h:
            clip = self.crop_or_pad_to_size(clip, target_w, target_h)
        return clip

    def crop_or_pad_to_size(self, clip, target_w, target_h):
        current_w, current_h = clip.size
        if current_w > target_w:
            try:
                from moviepy.video.fx.crop import crop
                x_center = current_w // 2
                x1 = x_center - target_w // 2; x2 = x_center + target_w // 2
                clip = clip.fx(crop, x1=x1, x2=x2)
            except Exception:
                pass
        elif current_w < target_w:
            pad_left = (target_w - current_w) // 2; pad_right = target_w - current_w - pad_left
            if MarginFunc is not None:
                clip = MarginFunc(clip, left=pad_left, right=pad_right, color=(0, 0, 0))
        if clip.h > target_h:
            try:
                from moviepy.video.fx.crop import crop
                y_center = clip.h // 2
                y1 = y_center - target_h // 2; y2 = y_center + target_h // 2
                clip = clip.fx(crop, y1=y1, y2=y2)
            except Exception:
                pass
        elif clip.h < target_h:
            pad_top = (target_h - clip.h) // 2; pad_bottom = target_h - clip.h - pad_top
            if MarginFunc is not None:
                clip = MarginFunc(clip, top=pad_top, bottom=pad_bottom, color=(0, 0, 0))
        return clip

    def write_video_file(self, clip, output_path, clip_id):
        codec = "libx264"
        preset = self.quality_preset.get()
        bitrate = self.bitrate.get()
        crf = str(self.crf.get())
        ffmpeg_params = ["-crf", crf]
        if self.include_audio.get() and getattr(clip, "audio", None) is not None:
            try:
                clip.write_videofile(
                    str(output_path), codec=codec, preset=preset, bitrate=bitrate,
                    audio_codec="aac", audio_bitrate=self.audio_bitrate.get(),
                    ffmpeg_params=ffmpeg_params, verbose=False, logger=None
                )
                self.message_queue.put(("log", f"✓ Successfully created: {output_path.name}"))
            except Exception:
                self.message_queue.put(("log", f"Audio failed for {clip_id}, retrying without audio..."))
                self.write_video_without_audio(clip, output_path, clip_id)
        else:
            self.write_video_without_audio(clip, output_path, clip_id)

    def write_video_without_audio(self, clip, output_path, clip_id):
        try:
            if getattr(clip, "audio", None) is not None:
                clip = clip.without_audio()
            clip.write_videofile(
                str(output_path), codec="libx264", preset=self.quality_preset.get(),
                bitrate=self.bitrate.get(), ffmpeg_params=["-crf", str(self.crf.get())],
                verbose=False, logger=None
            )
            self.message_queue.put(("log", f"✓ Successfully created (no audio): {output_path.name}"))
        except Exception as e:
            self.message_queue.put(("log", f"✗ Failed {clip_id}: {str(e)}"))
            raise

    # --- Patched Text Overlay (Pillow-based) ---
    def apply_text_overlay(self, clip, item):
        if not self.add_text_overlay.get():
            return clip
        template = self.overlay_text.get().strip() or "{label}"
        try:
            text_str = template.format(
                label=item.get("label", ""), id=item.get("id", ""),
                start=item.get("start", ""), end=item.get("end", "")
            )
        except Exception:
            text_str = template
        fontsize = max(20, min(120, int(self.overlay_fontsize.get())))
        color = self.overlay_color.get()
        font_paths = [
            "C:/Windows/Fonts/arial.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        ]
        font = None
        for path in font_paths:
            if Path(path).exists():
                try:
                    font = ImageFont.truetype(path, fontsize)
                    break
                except Exception:
                    continue
        if font is None:
            font = ImageFont.load_default()

        txt_img = Image.new("RGBA", (int(clip.w*0.9), fontsize*3), (0,0,0,0))
        draw = ImageDraw.Draw(txt_img)
        draw.text((10,0), text_str, font=font, fill=color, stroke_width=2, stroke_fill="black")

        import numpy as np
        txt_clip = ImageClip(np.array(txt_img)).set_duration(clip.duration)  # <-- fix applied

        mapping = {
            "top": ("center","top"), "center": ("center","center"), "bottom": ("center","bottom"),
            "top-left": ("left","top"), "top-right": ("right","top"),
            "bottom-left": ("left","bottom"), "bottom-right": ("right","bottom"),
        }
        pos = mapping.get(self.overlay_position.get(), ("center","bottom"))
        txt_clip = txt_clip.set_position(pos)
        return CompositeVideoClip([clip, txt_clip])


    # --- Thumbnail generation (unchanged) ---
    def generate_thumbnail(self, clip, item, output_dir: Path):
        if not self.generate_thumbnails.get():
            return
        option = self.thumb_time.get()
        try:
            if option == "start": t = min(0.5, max(0.01, clip.duration*0.01))
            elif option == "middle": t = clip.duration/2
            elif option == "end": t = max(0.5, clip.duration-0.5)
            elif option == "25%": t = clip.duration*0.25
            elif option == "75%": t = clip.duration*0.75
            elif option == "custom":
                try: t = float(self.thumb_custom_time.get()); t = min(max(0.0,t), clip.duration)
                except Exception: t = clip.duration/2
            else: t = clip.duration/2
        except Exception: t = clip.duration/2
        frame = clip.get_frame(t); img = Image.fromarray(frame)
        target_w, target_h = map(int, self.thumb_size.get().split("x"))
        img.thumbnail((target_w,target_h), Image.LANCZOS)
        bg = Image.new("RGB",(target_w,target_h),(0,0,0))
        bg.paste(img,((target_w-img.width)//2,(target_h-img.height)//2))
        safe_label = "".join(c if c.isalnum() else "_" for c in item.get("label",""))
        thumb_file = output_dir / f"{item.get('id','unknown')}_{safe_label}_thumb.jpg"
        bg.save(thumb_file,"JPEG",quality=95)
        self.message_queue.put(("log", f"Thumbnail saved: {thumb_file.name}"))

    def open_json_paste_dialog(self):
        dialog = JsonPasteDialog(self.root)
        self.root.wait_window(dialog.dialog)
        if dialog.result:
            out_dir = Path(self.output_folder.get() or ".")
            out_dir.mkdir(parents=True, exist_ok=True)
            temp_path = out_dir / "_pasted_clips.json"
            try:
                with open(temp_path, "w", encoding="utf-8") as f:
                    json.dump(dialog.result, f, indent=2)
                self.json_file_path.set(str(temp_path))
                messagebox.showinfo("JSON Loaded", f"Pasted JSON saved to:\n{temp_path}")
            except Exception as e:
                messagebox.showerror("Error", f"Failed to save JSON:\n{str(e)}")


class JsonPasteDialog:
    def __init__(self, parent):
        self.result = None
        self.dialog = tk.Toplevel(parent)
        self.dialog.title("Paste JSON Content")
        self.dialog.geometry("700x520")
        self.dialog.transient(parent)
        self.dialog.grab_set()
        self.create_widgets()
        try:
            clipboard_content = self.dialog.clipboard_get()
            if clipboard_content and (clipboard_content.strip().startswith('{') or clipboard_content.strip().startswith('[')):
                self.text_area.insert(1.0, clipboard_content)
                self.validate_json()
        except Exception: pass
        self.text_area.focus_set()

    def create_widgets(self):
        main_frame = ttk.Frame(self.dialog, padding="10"); main_frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(main_frame, text="Paste your JSON content below:").pack(anchor=tk.W, pady=(0,5))
        text_frame = ttk.Frame(main_frame); text_frame.pack(fill=tk.BOTH, expand=True, pady=(0,10))
        self.text_area = scrolledtext.ScrolledText(text_frame, height=20, width=90, wrap=tk.WORD)
        self.text_area.pack(fill=tk.BOTH, expand=True)
        self.status_var = tk.StringVar(value=""); status_label = ttk.Label(main_frame, textvariable=self.status_var)
        status_label.pack(anchor=tk.W, pady=(0,5))
        button_frame = ttk.Frame(main_frame); button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Show Sample Format", command=self.show_sample).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Cancel", command=self.cancel).pack(side=tk.RIGHT, padx=(5,0))
        self.ok_button = ttk.Button(button_frame, text="Load JSON", command=self.load_json); self.ok_button.pack(side=tk.RIGHT)
        self.dialog.bind('<Control-Return>', lambda e: self.load_json())
        self.text_area.bind('<KeyRelease>', lambda e: self.validate_json())
        self.ok_button.state(['disabled'])

    def show_sample(self):
        sample_json = '''{
  "src": "path/to/your/video.mp4",
  "clips": [
    {"id": "clip001", "start": 10.5, "end": 25.0, "label": "Introduction"},
    {"id": "clip002", "start": 45.2, "end": 67.8, "label": "Main Content"}
  ]
}'''
        self.text_area.delete(1.0, tk.END)
        self.text_area.insert(1.0, sample_json)
        self.validate_json()

    def validate_json(self):
        content = self.text_area.get(1.0, tk.END).strip()
        if not content: self.status_var.set("Paste JSON or use Show Sample."); self.ok_button.state(['disabled']); return False
        try: parsed = json.loads(content)
        except json.JSONDecodeError as e:
            self.status_var.set(f"JSON syntax error: {str(e)}"); self.ok_button.state(['disabled']); return False
        if not isinstance(parsed, dict): self.status_var.set("Top-level JSON must be an object."); self.ok_button.state(['disabled']); return False
        if "src" not in parsed: self.status_var.set("Missing 'src' field."); self.ok_button.state(['disabled']); return False
        if "clips" not in parsed or not isinstance(parsed["clips"], list): self.status_var.set("Missing 'clips' array."); self.ok_button.state(['disabled']); return False
        for i, clip in enumerate(parsed["clips"], start=1):
            if not isinstance(clip, dict): self.status_var.set(f"Clip {i} must be an object."); self.ok_button.state(['disabled']); return False
            for field in ("id","start","end","label"):
                if field not in clip: self.status_var.set(f"Clip {i} missing field '{field}'"); self.ok_button.state(['disabled']); return False
        self.status_var.set("JSON looks valid ✓"); self.ok_button.state(['!disabled']); return True

    def load_json(self):
        content = self.text_area.get(1.0, tk.END).strip()
        if not content: messagebox.showerror("Error","Please paste JSON."); return
        if not self.validate_json(): messagebox.showerror("Error","Invalid JSON."); return
        try: self.result = json.loads(content); self.dialog.destroy()
        except Exception as e: messagebox.showerror("Error", f"Failed to parse JSON:\n{str(e)}")

    def cancel(self): self.result = None; self.dialog.destroy()


def main():
    root = tk.Tk()
    app = VideoClipProcessorGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
