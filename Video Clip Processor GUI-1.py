import tkinter as tk
from tkinter import ttk, filedialog, messagebox, scrolledtext
import threading
import json
import sys
from pathlib import Path
from moviepy.video.io.VideoFileClip import VideoFileClip
from moviepy.video.VideoClip import ColorClip
import queue
import os

# Try importing margin / Margin depending on MoviePy version
try:
    from moviepy.video.fx.margin import margin as MarginFunc
except ImportError:
    try:
        from moviepy.video.fx.margin import Margin as MarginFunc
    except ImportError:
        raise ImportError("Could not find margin/Margin in moviepy. Check your MoviePy installation.")

class VideoClipProcessorGUI:
    def __init__(self, root):
        self.root = root
        self.root.title("Video Clip Processor")
        self.root.geometry("800x700")
        
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
        
        row = 0
        
        # JSON file selection
        ttk.Label(main_frame, text="Clips Recipe (JSON):").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.json_file_path, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="Browse", command=self.browse_json_file).grid(row=row, column=2, padx=(5, 0))
        row += 1
        
        # Output folder selection
        ttk.Label(main_frame, text="Output Folder:").grid(row=row, column=0, sticky=tk.W, pady=5)
        ttk.Entry(main_frame, textvariable=self.output_folder, width=50).grid(row=row, column=1, sticky=(tk.W, tk.E), padx=(5, 5))
        ttk.Button(main_frame, text="Browse", command=self.browse_output_folder).grid(row=row, column=2, padx=(5, 0))
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Video format options
        format_frame = ttk.LabelFrame(main_frame, text="Video Format", padding="5")
        format_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        format_frame.columnconfigure(1, weight=1)
        
        ttk.Radiobutton(format_frame, text="Short-form (1080x1920)", variable=self.video_format, value="1080x1920").grid(row=0, column=0, sticky=tk.W)
        ttk.Radiobutton(format_frame, text="Landscape (1920x1080)", variable=self.video_format, value="1920x1080").grid(row=0, column=1, sticky=tk.W)
        ttk.Radiobutton(format_frame, text="Square (1080x1080)", variable=self.video_format, value="1080x1080").grid(row=0, column=2, sticky=tk.W)
        ttk.Radiobutton(format_frame, text="Original", variable=self.video_format, value="original").grid(row=1, column=0, sticky=tk.W)
        row += 1
        
        # Quality settings
        quality_frame = ttk.LabelFrame(main_frame, text="Quality Settings", padding="5")
        quality_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
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
        audio_frame.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        audio_frame.columnconfigure(2, weight=1)
        
        ttk.Checkbutton(audio_frame, text="Include Audio", variable=self.include_audio).grid(row=0, column=0, sticky=tk.W)
        ttk.Label(audio_frame, text="Audio Bitrate:").grid(row=0, column=1, sticky=tk.W, padx=(20, 5))
        audio_bitrate_combo = ttk.Combobox(audio_frame, textvariable=self.audio_bitrate, 
                                          values=["128k", "192k", "256k", "320k"], 
                                          width=10)
        audio_bitrate_combo.grid(row=0, column=2, sticky=tk.W)
        row += 1
        
        # Separator
        ttk.Separator(main_frame, orient='horizontal').grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=10)
        row += 1
        
        # Progress bar
        self.progress_var = tk.StringVar(value="Ready to process")
        ttk.Label(main_frame, textvariable=self.progress_var).grid(row=row, column=0, columnspan=3, sticky=tk.W)
        row += 1
        
        self.progress_bar = ttk.Progressbar(main_frame, mode='determinate')
        self.progress_bar.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        row += 1
        
        # Control buttons
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=row, column=0, columnspan=3, pady=10)
        
        self.process_button = ttk.Button(button_frame, text="Process Clips", command=self.start_processing)
        self.process_button.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(button_frame, text="Open Output Folder", command=self.open_output_folder).pack(side=tk.LEFT, padx=(0, 10))
        ttk.Button(button_frame, text="Clear Log", command=self.clear_log).pack(side=tk.LEFT)
        row += 1
        
        # Log area
        ttk.Label(main_frame, text="Processing Log:").grid(row=row, column=0, sticky=tk.W, pady=(10, 0))
        row += 1
        
        self.log_text = scrolledtext.ScrolledText(main_frame, height=15, width=80)
        self.log_text.grid(row=row, column=0, columnspan=3, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(5, 0))
        main_frame.rowconfigure(row, weight=1)
    
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
        """Add message to log text widget"""
        self.log_text.insert(tk.END, message + "\n")
        self.log_text.see(tk.END)
        self.root.update_idletasks()
    
    def update_progress(self, current, total, message=""):
        """Update progress bar and status"""
        if total > 0:
            progress_percent = (current / total) * 100
            self.progress_bar['value'] = progress_percent
        
        status = f"Processing {current}/{total}"
        if message:
            status += f" - {message}"
        self.progress_var.set(status)
        
        self.root.update_idletasks()
    
    def start_processing(self):
        if self.processing:
            return
        
        # Validation
        if not self.json_file_path.get():
            messagebox.showerror("Error", "Please select a JSON file.")
            return
        
        if not Path(self.json_file_path.get()).exists():
            messagebox.showerror("Error", "JSON file not found.")
            return
        
        # Create output directory
        output_path = Path(self.output_folder.get())
        output_path.mkdir(parents=True, exist_ok=True)
        
        # Start processing in separate thread
        self.processing = True
        self.process_button.config(text="Processing...", state="disabled")
        
        thread = threading.Thread(target=self.process_clips_thread)
        thread.daemon = True
        thread.start()
    
    def check_queue(self):
        """Check for messages from processing thread"""
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
        
        # Schedule next check
        self.root.after(100, self.check_queue)
    
    def process_clips_thread(self):
        """Process clips in background thread"""
        try:
            # Load JSON data
            with open(self.json_file_path.get(), "r", encoding="utf-8") as f:
                clips_data = json.load(f)
            
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
                start = item["start"]
                end = item["end"]
                label = item["label"]
                
                self.message_queue.put(("progress", (idx, total_clips, f"Cutting {item['id']}")))
                self.message_queue.put(("log", f"[{idx}/{total_clips}] Processing {item['id']}: {start} -> {end}"))
                
                try:
                    # Create subclip
                    subclip = video.subclip(start, end)
                    
                    # Apply video format
                    subclip = self.apply_video_format(subclip)
                    
                    # Set FPS
                    subclip = subclip.set_fps(self.fps.get())
                    
                    # Generate output filename
                    safe_label = label.replace(' ', '_').replace('—', '-').replace('/', '_').replace('\\', '_')
                    out_file = output_dir / f"{item['id']}_{safe_label}.mp4"
                    
                    # Write video file
                    self.write_video_file(subclip, out_file, item['id'])
                    
                    subclip.close()
                    success_count += 1
                    
                except Exception as e:
                    self.message_queue.put(("log", f"Error processing {item['id']}: {str(e)}"))
                    continue
            
            video.close()
            self.message_queue.put(("done", (success_count, total_clips)))
            
        except Exception as e:
            self.message_queue.put(("error", str(e)))
    
    def apply_video_format(self, clip):
        """Apply the selected video format to the clip"""
        format_choice = self.video_format.get()
        
        if format_choice == "original":
            return clip
        
        target_w, target_h = map(int, format_choice.split('x'))
        
        try:
            from moviepy.video.fx.resize import resize
            # Resize to fit target height, maintain aspect ratio
            if format_choice == "1080x1920":  # Portrait
                clip = clip.fx(resize, height=target_h)
            elif format_choice == "1920x1080":  # Landscape
                clip = clip.fx(resize, width=target_w)
            else:  # Square
                # Resize to fit the larger dimension
                if clip.w > clip.h:
                    clip = clip.fx(resize, width=target_w)
                else:
                    clip = clip.fx(resize, height=target_h)
        except ImportError:
            # Fallback for older versions
            if format_choice == "1080x1920":
                aspect_ratio = clip.w / clip.h
                new_width = int(target_h * aspect_ratio)
                clip = clip.resize((new_width, target_h))
            elif format_choice == "1920x1080":
                aspect_ratio = clip.w / clip.h
                new_height = int(target_w / aspect_ratio)
                clip = clip.resize((target_w, new_height))
            else:  # Square
                if clip.w > clip.h:
                    aspect_ratio = clip.w / clip.h
                    new_height = int(target_w / aspect_ratio)
                    clip = clip.resize((target_w, new_height))
                else:
                    aspect_ratio = clip.w / clip.h
                    new_width = int(target_h * aspect_ratio)
                    clip = clip.resize((new_width, target_h))
        
        # Crop or pad to exact dimensions
        if clip.w != target_w or clip.h != target_h:
            clip = self.crop_or_pad_to_size(clip, target_w, target_h)
        
        return clip
    
    def crop_or_pad_to_size(self, clip, target_w, target_h):
        """Crop or pad clip to exact target dimensions"""
        current_w, current_h = clip.size
        
        if current_w > target_w:
            # Crop width
            try:
                from moviepy.video.fx.crop import crop
                x_center = current_w // 2
                x1 = x_center - target_w // 2
                x2 = x_center + target_w // 2
                clip = clip.fx(crop, x1=x1, x2=x2)
            except ImportError:
                x_center = current_w // 2
                x1 = x_center - target_w // 2
                x2 = x_center + target_w // 2
                clip = clip.crop(x1=x1, x2=x2)
                
        elif current_w < target_w:
            # Pad width
            pad_left = (target_w - current_w) // 2
            pad_right = target_w - current_w - pad_left
            clip = MarginFunc(clip, left=pad_left, right=pad_right, color=(0, 0, 0))
        
        if clip.h > target_h:
            # Crop height
            try:
                from moviepy.video.fx.crop import crop
                y_center = clip.h // 2
                y1 = y_center - target_h // 2
                y2 = y_center + target_h // 2
                clip = clip.fx(crop, y1=y1, y2=y2)
            except ImportError:
                y_center = clip.h // 2
                y1 = y_center - target_h // 2
                y2 = y_center + target_h // 2
                clip = clip.crop(y1=y1, y2=y2)
                
        elif clip.h < target_h:
            # Pad height
            pad_top = (target_h - clip.h) // 2
            pad_bottom = target_h - clip.h - pad_top
            clip = MarginFunc(clip, top=pad_top, bottom=pad_bottom, color=(0, 0, 0))
        
        return clip
    
    def write_video_file(self, clip, output_path, clip_id):
        """Write video file with current settings"""
        # Prepare parameters
        codec = "libx264"
        preset = self.quality_preset.get()
        bitrate = self.bitrate.get()
        crf = str(self.crf.get())
        
        ffmpeg_params = ["-crf", crf]
        
        if self.include_audio.get() and clip.audio is not None:
            # With audio
            try:
                clip.write_videofile(
                    str(output_path),
                    codec=codec,
                    preset=preset,
                    bitrate=bitrate,
                    audio_codec="aac",
                    audio_bitrate=self.audio_bitrate.get(),
                    ffmpeg_params=ffmpeg_params,
                    verbose=False,
                    logger=None
                )
                self.message_queue.put(("log", f"✓ Successfully created: {output_path.name}"))
            except Exception as e:
                self.message_queue.put(("log", f"Audio processing failed for {clip_id}, trying without audio..."))
                self.write_video_without_audio(clip, output_path, clip_id)
        else:
            # Without audio
            self.write_video_without_audio(clip, output_path, clip_id)
    
    def write_video_without_audio(self, clip, output_path, clip_id):
        """Write video file without audio"""
        try:
            if clip.audio is not None:
                clip_no_audio = clip.without_audio()
            else:
                clip_no_audio = clip
                
            clip_no_audio.write_videofile(
                str(output_path),
                codec="libx264",
                preset=self.quality_preset.get(),
                bitrate=self.bitrate.get(),
                ffmpeg_params=["-crf", str(self.crf.get())],
                verbose=False,
                logger=None
            )
            
            if clip.audio is not None:
                clip_no_audio.close()
                
            self.message_queue.put(("log", f"✓ Successfully created (no audio): {output_path.name}"))
            
        except Exception as e:
            self.message_queue.put(("log", f"✗ Failed to process {clip_id}: {str(e)}"))
            raise

def main():
    root = tk.Tk()
    app = VideoClipProcessorGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()