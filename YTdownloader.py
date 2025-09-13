import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import subprocess
import sys

def select_directory():
    folder = filedialog.askdirectory()
    if folder:
        save_path.set(folder)

def download_mp3():
    url = url_entry.get().strip()
    folder = save_path.get().strip()

    if not url:
        messagebox.showerror("Error", "Please enter a YouTube URL.")
        return
    if not folder:
        messagebox.showerror("Error", "Please choose a save directory.")
        return

    try:
        status_label.config(text="Downloading MP3...", foreground="#005f73")
        root.update_idletasks()

        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-x", "--audio-format", "mp3",
            "-o", os.path.join(folder, "%(title)s.%(ext)s"),
            url
        ]
        subprocess.run(cmd, check=True)

        status_label.config(text="MP3 Download complete!", foreground="#0a9396")
        messagebox.showinfo("Success", "MP3 downloaded successfully.")

    except subprocess.CalledProcessError as e:
        status_label.config(text="Download failed", foreground="red")
        messagebox.showerror("Error", f"yt-dlp failed.\n{e}")
    except Exception as e:
        status_label.config(text="Error occurred", foreground="red")
        messagebox.showerror("Error", str(e))

def download_mp4():
    url = url_entry.get().strip()
    folder = save_path.get().strip()

    if not url:
        messagebox.showerror("Error", "Please enter a YouTube URL.")
        return
    if not folder:
        messagebox.showerror("Error", "Please choose a save directory.")
        return

    try:
        status_label.config(text="Downloading MP4...", foreground="#005f73")
        root.update_idletasks()

        cmd = [
            sys.executable, "-m", "yt_dlp",
            "-f", "mp4",
            "-o", os.path.join(folder, "%(title)s.%(ext)s"),
            url
        ]
        subprocess.run(cmd, check=True)

        status_label.config(text="MP4 Download complete!", foreground="#0a9396")
        messagebox.showinfo("Success", "MP4 downloaded successfully.")

    except subprocess.CalledProcessError as e:
        status_label.config(text="Download failed", foreground="red")
        messagebox.showerror("Error", f"yt-dlp failed.\n{e}")
    except Exception as e:
        status_label.config(text="Error occurred", foreground="red")
        messagebox.showerror("Error", str(e))

# ---- UI Setup ----
root = tk.Tk()
root.title("Eagles YouTube → MP3/MP4 Converter")
root.geometry("520x300")
root.resizable(False, False)

# Set eagle icon (make sure eagle.ico is in same folder)
try:
    root.iconbitmap("eagle.ico")
except Exception:
    pass

style = ttk.Style()
style.theme_use("clam")

# Eagle color palette
primary = "#0a9396"   # teal
secondary = "#ee9b00" # golden accent
bg_color = "#fdfcdc"  # light parchment

root.configure(bg=bg_color)
style.configure("TButton", font=("Segoe UI", 10, "bold"), padding=6, background=primary, foreground="white")
style.map("TButton", background=[("active", secondary)])
style.configure("TLabel", font=("Segoe UI", 10), background=bg_color)
style.configure("Header.TLabel", font=("Segoe UI", 14, "bold"), foreground=primary, background=bg_color)

save_path = tk.StringVar()

# Layout
header = ttk.Label(root, text="🦅 Eagles YouTube Converter", style="Header.TLabel")
header.pack(pady=12)

frame = ttk.Frame(root, padding=15)
frame.pack(fill="both", expand=True)

url_label = ttk.Label(frame, text="YouTube URL:")
url_label.grid(row=0, column=0, sticky="w")
url_entry = ttk.Entry(frame, width=50)
url_entry.grid(row=0, column=1, padx=5, pady=5)

path_label = ttk.Label(frame, text="Save to:")
path_label.grid(row=1, column=0, sticky="w")
path_entry = ttk.Entry(frame, textvariable=save_path, width=38)
path_entry.grid(row=1, column=1, sticky="w", padx=5, pady=5)

browse_button = ttk.Button(frame, text="Browse", command=select_directory)
browse_button.grid(row=1, column=2, padx=5)

# Buttons for MP3 and MP4
button_frame = ttk.Frame(root)
button_frame.pack(pady=10)

download_mp3_button = ttk.Button(button_frame, text="🎵 MP3", command=download_mp3)
download_mp3_button.grid(row=0, column=0, padx=10)

download_mp4_button = ttk.Button(button_frame, text="🎬 MP4", command=download_mp4)
download_mp4_button.grid(row=0, column=1, padx=10)

status_label = ttk.Label(root, text="", font=("Segoe UI", 9))
status_label.pack()

root.mainloop()
