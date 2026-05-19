import os
import sys
import json
import threading
import wave
import logging
from datetime import datetime
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import pystray
from PIL import Image, ImageDraw

from pyaudio import PyAudio, paInt16
from vosk import Model, KaldiRecognizer

from profanity_detector import detect_profanity
from profanity_list import PROFANITY_WORDS

try:
    import urllib.request
    import zipfile
    HAS_DOWNLOAD = True
except ImportError:
    HAS_DOWNLOAD = False


def resource_path(relative):
    if getattr(sys, 'frozen', False):
        base = sys._MEIPASS
    else:
        base = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, relative)


SETTINGS_FILE = "vm_settings.json"
DEFAULT_SETTINGS = {
    "recordings_dir": "",
    "profanity_words": PROFANITY_WORDS,
    "post_record_seconds": 3,
    "setup_complete": False,
}


def load_settings():
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
    if os.path.exists(path):
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    return DEFAULT_SETTINGS.copy()


def save_settings(settings):
    path = os.path.join(os.path.dirname(os.path.abspath(__file__)), SETTINGS_FILE)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(settings, f, indent=2, ensure_ascii=False)


def get_model_dir():
    base = os.path.dirname(os.path.abspath(__file__))
    if getattr(sys, 'frozen', False):
        return os.path.join(base, "model")
    return os.path.join(base, "models", "vosk-model-small-ru-0.22")


class SettingsDialog:
    def __init__(self, parent, settings):
        self.result = None
        self.settings = settings.copy()
        self.settings.setdefault("profanity_words", PROFANITY_WORDS)
        self.settings.setdefault("post_record_seconds", 3)

        self.win = tk.Toplevel(parent)
        self.win.title("Настройки")
        self.win.geometry("480x520")
        self.win.resizable(False, False)
        self.win.transient(parent)
        self.win.grab_set()

        bg = "#1e1e2e"
        fg = "#ffffff"
        accent = "#6c5ce7"
        self.win.configure(bg=bg)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(16, 6))
        style.configure("Accent.TButton", background=accent, foreground="white", font=("Segoe UI", 10, "bold"))
        style.configure("Header.TLabel", background=bg, foreground="#a29bfe", font=("Segoe UI", 13, "bold"))

        pady = 12
        padx = 24

        ttk.Label(self.win, text="Настройки", style="Header.TLabel").pack(anchor="w", padx=padx, pady=(20, 4))
        ttk.Label(self.win, text="Папка для записей:").pack(anchor="w", padx=padx, pady=(pady, 2))

        dir_frame = ttk.Frame(self.win)
        dir_frame.pack(fill="x", padx=padx)

        self.dir_var = tk.StringVar(value=self.settings.get("recordings_dir", ""))
        ttk.Entry(dir_frame, textvariable=self.dir_var, width=35).pack(side="left", fill="x", expand=True, padx=(0, 6))
        ttk.Button(dir_frame, text="Обзор...", command=self.browse_dir).pack(side="right")

        ttk.Label(self.win, text="Запись после детекции (сек):").pack(anchor="w", padx=padx, pady=(pady, 2))
        self.post_var = tk.IntVar(value=self.settings.get("post_record_seconds", 3))
        ttk.Spinbox(self.win, from_=1, to=30, textvariable=self.post_var, width=5).pack(anchor="w", padx=padx)

        ttk.Label(self.win, text="Слова для поиска (каждое с новой строки):").pack(anchor="w", padx=padx, pady=(pady, 2))

        self.words_text = tk.Text(self.win, height=12, width=50, bg="#2a2a3e", fg=fg, insertbackground=fg,
                                  font=("Consolas", 9), relief="flat")
        self.words_text.pack(fill="both", padx=padx, expand=True)
        self.words_text.insert("1.0", "\n".join(self.settings.get("profanity_words", PROFANITY_WORDS)))

        btn_frame = ttk.Frame(self.win)
        btn_frame.pack(fill="x", padx=padx, pady=(pady, 16))

        ttk.Button(btn_frame, text="Сохранить", style="Accent.TButton", command=self.save).pack(side="right", padx=(6, 0))
        ttk.Button(btn_frame, text="Отмена", command=self.win.destroy).pack(side="right")

    def browse_dir(self):
        d = filedialog.askdirectory(title="Выберите папку для записей")
        if d:
            self.dir_var.set(d)

    def save(self):
        rec_dir = self.dir_var.get().strip()
        if not rec_dir:
            messagebox.showwarning("Внимание", "Укажите папку для записей.")
            return

        self.settings["recordings_dir"] = rec_dir
        self.settings["post_record_seconds"] = self.post_var.get()
        self.settings["profanity_words"] = [w.strip().lower() for w in self.words_text.get("1.0", "end-1c").split("\n") if w.strip()]
        self.settings["setup_complete"] = True
        self.result = self.settings
        self.win.destroy()


class SetupWizard:
    def __init__(self, root):
        self.result = None
        self.win = tk.Toplevel(root)
        self.win.title("VoiceMonitor — Настройка")
        self.win.geometry("520x400")
        self.win.resizable(False, False)
        self.win.transient(root)
        self.win.grab_set()

        bg = "#1e1e2e"
        fg = "#ffffff"
        self.win.configure(bg=bg)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TLabel", background=bg, foreground=fg, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 10), padding=(16, 6))
        style.configure("Accent.TButton", background="#6c5ce7", foreground="white", font=("Segoe UI", 10, "bold"))
        style.configure("Title.TLabel", background=bg, foreground="#a29bfe", font=("Segoe UI", 14, "bold"))
        style.configure("Subtitle.TLabel", background=bg, foreground="#a0a0b0", font=("Segoe UI", 9))

        ttk.Label(self.win, text="Добро пожаловать!", style="Title.TLabel").pack(anchor="w", padx=24, pady=(24, 4))
        ttk.Label(self.win, text="Первый запуск VoiceMonitor. Выберите папку для записей:").pack(anchor="w", padx=24)

        self.dir_var = tk.StringVar()
        self.mode_var = tk.StringVar(value="default")

        opts = [
            ("default", "Рядом с программой (рекомендуется)"),
            ("docs", "Документы \\ VoiceMonitor"),
            ("desktop", "Рабочий стол \\ VoiceMonitor"),
            ("custom", "Выбрать свою папку..."),
        ]
        for val, txt in opts:
            ttk.Radiobutton(self.win, text=txt, variable=self.mode_var, value=val).pack(anchor="w", padx=24, pady=2)

        self.custom_frame = ttk.Frame(self.win)
        self.custom_frame.pack(fill="x", padx=48, pady=4)
        ttk.Entry(self.custom_frame, textvariable=self.dir_var, width=30).pack(side="left", fill="x", expand=True, padx=(0, 4))
        ttk.Button(self.custom_frame, text="...", command=self.browse).pack(side="right")
        self.custom_frame.pack_forget()

        self.mode_var.trace_add("write", self._on_mode)

        ttk.Separator(self.win, orient="horizontal").pack(fill="x", padx=24, pady=12)

        btn_f = ttk.Frame(self.win)
        btn_f.pack(fill="x", padx=24)
        ttk.Button(btn_f, text="Сохранить и начать", style="Accent.TButton", command=self.apply).pack(side="right")

        ttk.Label(self.win, text="Настройки можно изменить позже через кнопку ⚙", style="Subtitle.TLabel").pack(anchor="w", padx=24, pady=(6, 16))

    def _on_mode(self, *args):
        if self.mode_var.get() == "custom":
            self.custom_frame.pack(fill="x", padx=48, pady=4)
        else:
            self.custom_frame.pack_forget()

    def browse(self):
        d = filedialog.askdirectory()
        if d:
            self.dir_var.set(d)

    def apply(self):
        mode = self.mode_var.get()
        base = os.path.dirname(os.path.abspath(__file__))
        if mode == "default":
            path = os.path.join(base, "recordings")
        elif mode == "docs":
            path = os.path.join(os.path.expanduser("~/Documents"), "VoiceMonitor")
        elif mode == "desktop":
            path = os.path.join(os.path.expanduser("~/Desktop"), "VoiceMonitor")
        else:
            path = self.dir_var.get().strip()
            if not path:
                messagebox.showwarning("Внимание", "Выберите папку.")
                return

        try:
            os.makedirs(path, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Ошибка", str(e))
            return

        self.result = {
            "recordings_dir": path,
            "profanity_words": PROFANITY_WORDS,
            "post_record_seconds": 3,
            "setup_complete": True,
        }
        save_settings(self.result)
        messagebox.showinfo("Готово", f"Записи: {path}")
        self.win.destroy()


class VoiceMonitorApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("VoiceMonitor — Контроль речи")
        self.root.geometry("880x580")
        self.root.minsize(700, 450)

        bg = "#1e1e2e"
        accent = "#6c5ce7"
        light = "#a29bfe"
        self.root.configure(bg=bg)

        style = ttk.Style()
        style.theme_use("clam")
        style.configure("Treeview", background="#2a2a3e", foreground="#ffffff", fieldbackground="#2a2a3e",
                        borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#3a3a4e", foreground=light,
                        font=("Segoe UI", 9, "bold"), borderwidth=0)
        style.map("Treeview.Heading", background=[("active", "#4a4a5e")])
        style.map("Treeview", background=[("selected", accent)])
        style.configure("TButton", padding=(12, 4))
        style.configure("TFrame", background=bg)
        style.configure("TLabel", background=bg, foreground="#ffffff")

        self.settings = load_settings()
        self.running = False
        self.monitor_thread = None
        self.model = None
        self.recognizer = None
        self.wave_in = None
        self.audio_buffer = []
        self.is_post_recording = False
        self.post_chunks = 0
        self.detection_time = None
        self.detection_text = ""

        self._check_setup()
        self._build_ui()
        self._load_model()
        self._load_log()

    def _check_setup(self):
        if not self.settings.get("setup_complete"):
            wizard = SetupWizard(self.root)
            self.root.wait_window(wizard.win)
            if wizard.result:
                self.settings = wizard.result
            else:
                self.root.quit()
                exit(0)

        rec_dir = self.settings.get("recordings_dir", "")
        if rec_dir:
            os.makedirs(rec_dir, exist_ok=True)

    def _build_ui(self):
        top = tk.Frame(self.root, bg="#2d2d44", height=50)
        top.pack(fill="x", padx=0, pady=0)
        top.pack_propagate(False)

        self.btn_start = tk.Button(top, text="▶  Старт", bg="#28a745", fg="white", relief="flat",
                                   font=("Segoe UI", 9, "bold"), cursor="hand2", padx=12, pady=6,
                                   command=self.start_monitoring)
        self.btn_start.pack(side="left", padx=(12, 6), pady=10)

        self.btn_stop = tk.Button(top, text="■  Стоп", bg="#dc3545", fg="white", relief="flat",
                                  font=("Segoe UI", 9, "bold"), cursor="hand2", padx=12, pady=6,
                                  state="disabled", command=self.stop_monitoring)
        self.btn_stop.pack(side="left", padx=6, pady=10)

        tk.Button(top, text="⚙  Настройки", bg="#6c5ce7", fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"), cursor="hand2", padx=12, pady=6,
                  command=self.show_settings).pack(side="left", padx=6, pady=10)

        tk.Button(top, text="📂  Папка", bg="#6c5ce7", fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"), cursor="hand2", padx=12, pady=6,
                  command=self.open_folder).pack(side="left", padx=6, pady=10)

        tk.Button(top, text="🗑  Очистить", bg="#6c5ce7", fg="white", relief="flat",
                  font=("Segoe UI", 9, "bold"), cursor="hand2", padx=12, pady=6,
                  command=self.clear_log).pack(side="left", padx=6, pady=10)

        tree_frame = tk.Frame(self.root, bg="#1e1e2e")
        tree_frame.pack(fill="both", expand=True, padx=12, pady=12)

        columns = ("date", "time", "text", "file")
        self.tree = ttk.Treeview(tree_frame, columns=columns, show="headings", height=20)

        self.tree.heading("date", text="Дата")
        self.tree.heading("time", text="Время")
        self.tree.heading("text", text="Распознанный текст")
        self.tree.heading("file", text="Файл")

        self.tree.column("date", width=85, anchor="center")
        self.tree.column("time", width=75, anchor="center")
        self.tree.column("text", width=340)
        self.tree.column("file", width=200)

        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=vsb.set)

        self.tree.pack(side="left", fill="both", expand=True)
        vsb.pack(side="right", fill="y")

        self.tree.bind("<Double-1>", self.on_double_click)

        self.status_bar = tk.Frame(self.root, bg="#1e1e2e", height=28)
        self.status_bar.pack(fill="x", side="bottom")
        self.status_label = tk.Label(self.status_bar, text="Готово", bg="#1e1e2e", fg="#a29bfe", font=("Segoe UI", 9))
        self.status_label.pack(side="left", padx=12)

    def _load_model(self):
        model_dir = get_model_dir()
        if os.path.exists(model_dir) and len(os.listdir(model_dir)) > 3:
            try:
                self.model = Model(model_dir)
                self.recognizer = KaldiRecognizer(self.model, 16000)
                self.recognizer.SetWords(True)
                self.status_label.config(text="Модель загружена. Нажмите «Старт».", fg="#28a745")
                return
            except Exception as e:
                self.status_label.config(text=f"Ошибка модели: {e}", fg="#dc3545")

        self._show_download_dialog(model_dir)

    def _show_download_dialog(self, model_dir):
        dlg = tk.Toplevel(self.root)
        dlg.title("Скачать модель")
        dlg.geometry("420x280")
        dlg.resizable(False, False)
        dlg.transient(self.root)
        dlg.grab_set()
        dlg.configure(bg="#1e1e2e")

        ttk.Label(dlg, text="Модель распознавания речи не найдена",
                  font=("Segoe UI", 11, "bold"), foreground="#a29bfe",
                  background="#1e1e2e").pack(pady=(24, 8))

        ttk.Label(dlg, text="Требуется скачать модель (~50 MB).\nЭто нужно сделать один раз.",
                  foreground="#a0a0b0", background="#1e1e2e",
                  justify="center").pack(pady=(0, 16))

        progress = ttk.Progressbar(dlg, mode="determinate", length=320)
        progress.pack(pady=8)

        status_lbl = ttk.Label(dlg, text="", foreground="#a0a0b0", background="#1e1e2e")
        status_lbl.pack()

        def do_download():
            btn.config(state="disabled")
            url = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
            zip_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_model_temp.zip")

            try:
                def report(block, total, size):
                    if total > 0:
                        pct = int(block * size * 100 / total)
                        self.root.after(0, lambda: (progress.configure(value=pct), status_lbl.config(text=f"Скачивание: {pct}%")))

                urllib.request.urlretrieve(url, zip_path, reporthook=report)
                self.root.after(0, lambda: status_lbl.config(text="Распаковка..."))

                os.makedirs(model_dir, exist_ok=True)
                with zipfile.ZipFile(zip_path, 'r') as z:
                    z.extractall(model_dir)
                os.remove(zip_path)

                inner = os.path.join(model_dir, "vosk-model-small-ru-0.22")
                if os.path.exists(inner):
                    for f in os.listdir(inner):
                        src = os.path.join(inner, f)
                        dst = os.path.join(model_dir, f)
                        if os.path.exists(dst):
                            if os.path.isdir(dst):
                                import shutil
                                shutil.rmtree(dst)
                            else:
                                os.remove(dst)
                        if os.path.isdir(src):
                            import shutil
                            shutil.move(src, dst)
                        else:
                            os.rename(src, dst)
                    os.rmdir(inner)

                self.root.after(0, lambda: status_lbl.config(text="✓ Модель установлена!", foreground="#28a745"))
                self.root.after(500, lambda: (dlg.destroy(), self._load_model()))
            except Exception as e:
                self.root.after(0, lambda: (status_lbl.config(text=f"✗ Ошибка: {str(e)[:80]}", foreground="#dc3545"), btn.config(state="normal")))

        btn = tk.Button(dlg, text="Скачать модель", bg="#6c5ce7", fg="white", relief="flat",
                        font=("Segoe UI", 10, "bold"), cursor="hand2", padx=20, pady=8,
                        command=lambda: threading.Thread(target=do_download, daemon=True).start())
        btn.pack(pady=(16, 8))

        ttk.Label(dlg, text="Или скачайте вручную и распакуйте в models/",
                  foreground="#666666", background="#1e1e2e",
                  font=("Segoe UI", 8)).pack()

    def start_monitoring(self):
        if not self.model:
            messagebox.showwarning("Ошибка", "Модель не загружена.")
            return
        self.running = True
        self.btn_start.config(state="disabled")
        self.btn_stop.config(state="normal")
        self.status_label.config(text="● Мониторинг активен", fg="#28a745")
        self.audio_buffer = []
        self.is_post_recording = False
        self.post_chunks = 0

        self.monitor_thread = threading.Thread(target=self._monitor_loop, daemon=True)
        self.monitor_thread.start()

    def stop_monitoring(self):
        self.running = False
        self.btn_start.config(state="normal")
        self.btn_stop.config(state="disabled")
        self.status_label.config(text="Готово", fg="#a29bfe")

    def _monitor_loop(self):
        pa = PyAudio()
        chunk_size = 3200
        post_total = self.settings.get("post_record_seconds", 3) * 5

        try:
            stream = pa.open(format=paInt16, channels=1, rate=16000, input=True,
                             frames_per_buffer=chunk_size)
        except Exception as e:
            self.root.after(0, lambda: messagebox.showerror("Ошибка", str(e)))
            return

        try:
            while self.running:
                try:
                    data = stream.read(chunk_size, exception_on_overflow=False)
                except Exception:
                    continue

                self.audio_buffer.append(data)

                if self.recognizer.AcceptWaveform(data):
                    result = json.loads(self.recognizer.Result())
                    text = result.get("text", "")
                    if text:
                        is_prof, found = self._check_profanity(text)
                        if is_prof:
                            self.detection_time = datetime.now()
                            self.detection_text = f"{text} [{found}]"
                            self.is_post_recording = True
                            self.post_chunks = 0
                            continue

                if self.is_post_recording:
                    self.post_chunks += 1
                    if self.post_chunks >= post_total:
                        self._save_recording()
                        self.is_post_recording = False
                        self.post_chunks = 0
                        self.audio_buffer = []

        finally:
            stream.stop_stream()
            stream.close()
            pa.terminate()

    def _check_profanity(self, text):
        is_prof, found = detect_profanity(text)
        if is_prof:
            return True, found
        words = self.settings.get("profanity_words", PROFANITY_WORDS)
        for w in words:
            if w in text.lower():
                return True, w
        return False, ""

    def _save_recording(self):
        try:
            ts = self.detection_time.strftime("%Y-%m-%d_%H-%M-%S")
            filename = f"detect_{ts}.wav"
            rec_dir = self.settings.get("recordings_dir", "")
            filepath = os.path.join(rec_dir, filename)

            audio_data = b"".join(self.audio_buffer)
            with wave.open(filepath, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(16000)
                wf.writeframes(audio_data)

            log_path = os.path.join(rec_dir, f"detections_{datetime.now().strftime('%Y-%m')}.json")
            entries = []
            if os.path.exists(log_path):
                with open(log_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)

            entry = {
                "date": self.detection_time.strftime("%d.%m.%Y"),
                "time": self.detection_time.strftime("%H:%M:%S"),
                "text": self.detection_text,
                "file": filename,
            }
            entries.append(entry)
            with open(log_path, "w", encoding="utf-8") as f:
                json.dump(entries, f, indent=2, ensure_ascii=False)

            self.root.after(0, lambda: self.tree.insert("", 0, values=(entry["date"], entry["time"], entry["text"], entry["file"])))
            self.root.after(0, lambda: self.status_label.config(text=f"Детекция: {entry['time']} — {entry['text'][:50]}"))

        except Exception as e:
            print(f"Save error: {e}")

    def _load_log(self):
        rec_dir = self.settings.get("recordings_dir", "")
        if not os.path.exists(rec_dir):
            return
        import glob
        logs = sorted(glob.glob(os.path.join(rec_dir, "detections_*.json")), reverse=True)[:10]
        for log_path in logs:
            try:
                with open(log_path, "r", encoding="utf-8") as f:
                    entries = json.load(f)
                for entry in reversed(entries):
                    self.tree.insert("", 0, values=(entry["date"], entry["time"], entry["text"], entry["file"]))
            except Exception:
                pass

    def show_settings(self):
        dlg = SettingsDialog(self.root, self.settings)
        self.root.wait_window(dlg.win)
        if dlg.result:
            self.settings = dlg.result
            save_settings(self.settings)
            rec_dir = self.settings.get("recordings_dir", "")
            if rec_dir:
                os.makedirs(rec_dir, exist_ok=True)

    def open_folder(self):
        rec_dir = self.settings.get("recordings_dir", "")
        if os.path.exists(rec_dir):
            os.startfile(rec_dir)

    def clear_log(self):
        if messagebox.askyesno("Очистить", "Удалить все записи?"):
            rec_dir = self.settings.get("recordings_dir", "")
            if os.path.exists(rec_dir):
                import glob
                for f in glob.glob(os.path.join(rec_dir, "detections_*.json")):
                    os.remove(f)
                for f in glob.glob(os.path.join(rec_dir, "detect_*.wav")):
                    os.remove(f)
            for item in self.tree.get_children():
                self.tree.delete(item)
            self.status_label.config(text="Журнал очищен")

    def on_double_click(self, event):
        item = self.tree.selection()
        if not item:
            return
        values = self.tree.item(item[0], "values")
        if len(values) < 4:
            return
        filename = values[3]
        rec_dir = self.settings.get("recordings_dir", "")
        filepath = os.path.join(rec_dir, filename)
        if os.path.exists(filepath):
            os.startfile(filepath)

    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = VoiceMonitorApp()
    app.run()
